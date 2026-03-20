/*
 * ZMQ Channel Broker — RF Channel Impairment Simulator for srsRAN ZMQ Radio
 *
 * Sits between gNB and UE ZMQ sockets, forwarding IQ samples while
 * applying channel impairments:
 *   - AWGN (Additive White Gaussian Noise) — always active
 *   - Rayleigh flat fading — optional, enabled with --fading
 *
 * Port topology:
 *   gNB TX (REP bind :4000) → Broker DL (REQ→4000, impair, REP bind :2000) → UE RX (REQ→2000)
 *   UE  TX (REP bind :2001) → Broker UL (REQ→2001, impair, REP bind :4001) → gNB RX (REQ→4001)
 *
 * Build:  gcc -O2 -o zmq_channel_broker zmq_channel_broker.c -lzmq -lm -lpthread
 * Usage:  ./zmq_channel_broker [--snr <dB>] [--fading] [--doppler <Hz>]
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <pthread.h>
#include <signal.h>
#include <time.h>
#include <zmq.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#define MAX_BUF_SIZE    (4 * 1024 * 1024) /* 4 MB — enough for any subframe */
#define DEFAULT_SRATE   23.04e6f          /* srsRAN ZMQ sample rate */

static volatile int running = 1;

static void sig_handler(int sig) {
    (void)sig;
    running = 0;
}

/* ── Random Number Generation ─────────────────────────────────────────────── */

/* Box-Muller: generate two independent N(0,1) samples (for I and Q) */
static inline void randn_pair(unsigned int *seed, float *n1, float *n2) {
    float u1 = ((float)rand_r(seed) + 1.0f) / ((float)RAND_MAX + 1.0f);
    float u2 = ((float)rand_r(seed) + 1.0f) / ((float)RAND_MAX + 1.0f);
    float r  = sqrtf(-2.0f * logf(u1));
    *n1 = r * cosf(2.0f * (float)M_PI * u2);
    *n2 = r * sinf(2.0f * (float)M_PI * u2);
}

/* ── Rician / Rayleigh Flat Fading Model ───────────────────────────────────── *
 *
 * First-order autoregressive (AR1) model for time-correlated flat fading,
 * extended with an optional Line-of-Sight (LoS) component (Rician fading).
 *
 * Scatter (NLOS) component, updated once per subframe:
 *   h_I[n] = α · h_I[n-1] + σ_inn · N(0,1)
 *   h_Q[n] = α · h_Q[n-1] + σ_inn · N(0,1)
 *
 * Total channel coefficient:
 *   h = √(K/(K+1)) · 1.0  +  √(1/(K+1)) · (h_I + j·h_Q)
 *       └── LoS (fixed) ──┘   └── scattered (fading) ──┘
 *
 * where:
 *   K       = Rician K-factor (linear). K=0 → pure Rayleigh, K→∞ → AWGN-like.
 *   α       = J₀(2π · f_d · T)            (Jake's model, Bessel autocorrelation)
 *   σ_inn   = √((1 - α²) · 0.5)           (innovation std, preserves E[|h_s|²]=1)
 *   T       = num_iq_pairs / sample_rate   (subframe duration)
 *   f_d     = max Doppler frequency (Hz)
 *
 * Properties:
 *   - E[|h|²] = 1.0  (unit mean power, no long-term gain/loss)
 *   - K > 0 prevents deep nulls: minimum gain ≈ (√(K/(K+1)) - √(1/(K+1)))²
 *   - K = 6 dB (≈4)  → minimum ~-6 dB fade (pedestrian with LoS)
 *   - K = 0          → pure Rayleigh (deep fades, can crash UE)
 *   - Higher Doppler  = faster fades = more time-varying telemetry
 * ─────────────────────────────────────────────────────────────────────────── */

typedef struct {
    float h_I;            /* real part of scatter component */
    float h_Q;            /* imaginary part of scatter component */
    int   enabled;        /* fading active? */
    float doppler_hz;     /* max Doppler frequency */
    float sample_rate;    /* IQ sample rate (Hz) */
    float k_factor;       /* Rician K-factor (linear, 0 = pure Rayleigh) */
    float los_amp;        /* √(K/(K+1)) — LoS amplitude */
    float scatter_amp;    /* √(1/(K+1)) — scatter amplitude */
} fading_state_t;

static void fading_init(fading_state_t *f, int enabled, float doppler_hz,
                        float sample_rate, float k_factor_db,
                        unsigned int *seed) {
    f->enabled     = enabled;
    f->doppler_hz  = doppler_hz;
    f->sample_rate = sample_rate;
    /* Convert K-factor from dB to linear */
    f->k_factor    = powf(10.0f, k_factor_db / 10.0f);
    float Kp1      = f->k_factor + 1.0f;
    f->los_amp     = sqrtf(f->k_factor / Kp1);
    f->scatter_amp = sqrtf(1.0f / Kp1);
    if (enabled) {
        /* Start at a random point on the distribution */
        float n1, n2;
        randn_pair(seed, &n1, &n2);
        f->h_I = n1 * 0.7071f;  /* √0.5 for unit mean |h_scatter|² */
        f->h_Q = n2 * 0.7071f;
    } else {
        f->h_I = 1.0f;
        f->h_Q = 0.0f;
    }
}

/* Advance fading state by one subframe of num_iq_pairs complex samples */
static void fading_update(fading_state_t *f, int num_iq_pairs, unsigned int *seed) {
    if (!f->enabled) return;

    double T     = (double)num_iq_pairs / (double)f->sample_rate;
    float  alpha = (float)j0(2.0 * M_PI * (double)f->doppler_hz * T);
    float  a2    = alpha * alpha;
    float  sigma = sqrtf(fmaxf(0.0f, (1.0f - a2) * 0.5f));

    float n1, n2;
    randn_pair(seed, &n1, &n2);
    f->h_I = alpha * f->h_I + sigma * n1;
    f->h_Q = alpha * f->h_Q + sigma * n2;
}

/* Apply fading: complex-multiply each IQ pair by h_total
 * h_total = los_amp * 1.0  +  scatter_amp * (h_I + j*h_Q)  */
static void fading_apply(const fading_state_t *f, float *samples, int nfloats) {
    if (!f->enabled) return;
    /* Combine LoS (real-only, phase=0) and scatter components */
    float hI = f->los_amp + f->scatter_amp * f->h_I;
    float hQ =              f->scatter_amp * f->h_Q;
    for (int i = 0; i + 1 < nfloats; i += 2) {
        float I = samples[i];
        float Q = samples[i + 1];
        samples[i]     = hI * I - hQ * Q;   /* Re{h · x} */
        samples[i + 1] = hI * Q + hQ * I;   /* Im{h · x} */
    }
}

/* Instantaneous channel gain in dB: 10·log10(|h_total|²) */
static inline float fading_gain_db(const fading_state_t *f) {
    float hI = f->los_amp + f->scatter_amp * f->h_I;
    float hQ =              f->scatter_amp * f->h_Q;
    float g  = hI * hI + hQ * hQ;
    return (g > 1e-30f) ? 10.0f * log10f(g) : -300.0f;
}

/* ── Channel Thread ───────────────────────────────────────────────────────── */

typedef struct {
    const char *name;
    const char *rep_bind_addr;    /* broker binds REP here (downstream endpoint) */
    const char *req_connect_addr; /* broker connects REQ here (upstream endpoint) */
    float       snr_db;
    int         fading_enabled;
    float       doppler_hz;
    float       k_factor_db;     /* Rician K-factor in dB (0 = Rayleigh) */
    float       sample_rate;
    void       *zmq_ctx;
    unsigned int rng_seed;
} channel_args_t;

static void *channel_thread(void *arg) {
    channel_args_t *ch = (channel_args_t *)arg;

    float snr_linear = powf(10.0f, ch->snr_db / 10.0f);
    unsigned int seed = ch->rng_seed;

    /* Initialize fading model */
    fading_state_t fading;
    fading_init(&fading, ch->fading_enabled, ch->doppler_hz,
                ch->sample_rate, ch->k_factor_db, &seed);

    /* Create sockets */
    void *rep = zmq_socket(ch->zmq_ctx, ZMQ_REP);
    void *req = zmq_socket(ch->zmq_ctx, ZMQ_REQ);

    if (zmq_bind(rep, ch->rep_bind_addr) != 0) {
        fprintf(stderr, "[%s] FATAL: bind REP on %s: %s\n",
                ch->name, ch->rep_bind_addr, zmq_strerror(zmq_errno()));
        return NULL;
    }
    if (zmq_connect(req, ch->req_connect_addr) != 0) {
        fprintf(stderr, "[%s] FATAL: connect REQ to %s: %s\n",
                ch->name, ch->req_connect_addr, zmq_strerror(zmq_errno()));
        return NULL;
    }

    if (ch->fading_enabled) {
        printf("[%s] Active: upstream %s → Rician(K=%.1f dB, fd=%.0f Hz)+AWGN(SNR=%.1f dB) → downstream %s\n",
               ch->name, ch->req_connect_addr, ch->k_factor_db, ch->doppler_hz, ch->snr_db, ch->rep_bind_addr);
    } else {
        printf("[%s] Active: upstream %s → AWGN(SNR=%.1f dB) → downstream %s\n",
               ch->name, ch->req_connect_addr, ch->snr_db, ch->rep_bind_addr);
    }

    uint8_t *buf     = (uint8_t *)malloc(MAX_BUF_SIZE);
    uint8_t *req_buf = (uint8_t *)malloc(MAX_BUF_SIZE);

    unsigned long msg_count    = 0;
    unsigned long total_samples = 0;
    float min_gain_db = 0.0f, max_gain_db = 0.0f;

    /* Socket timeout so we can check the 'running' flag periodically */
    int timeout_ms = 500;
    zmq_setsockopt(rep, ZMQ_RCVTIMEO, &timeout_ms, sizeof(timeout_ms));
    zmq_setsockopt(rep, ZMQ_SNDTIMEO, &timeout_ms, sizeof(timeout_ms));
    zmq_setsockopt(req, ZMQ_RCVTIMEO, &timeout_ms, sizeof(timeout_ms));
    zmq_setsockopt(req, ZMQ_SNDTIMEO, &timeout_ms, sizeof(timeout_ms));

    while (running) {
        /* 1. Receive request from downstream (UE-RX or gNB-RX)
         *    REP is in "recv" state — EAGAIN/EINTR just mean retry. */
        int rlen;
        while (running) {
            rlen = zmq_recv(rep, req_buf, MAX_BUF_SIZE, 0);
            if (rlen >= 0) break;
            int e = zmq_errno();
            if (e == EAGAIN || e == EINTR) continue;
            fprintf(stderr, "[%s] recv(rep) error: %s\n", ch->name, zmq_strerror(e));
            goto done;
        }
        if (!running) break;

        /* 2. Forward request to upstream (gNB-TX or UE-TX)
         *    REQ send — retry on EAGAIN/EINTR. */
        while (running) {
            if (zmq_send(req, req_buf, rlen, 0) >= 0) break;
            int e = zmq_errno();
            if (e == EAGAIN || e == EINTR) continue;
            fprintf(stderr, "[%s] send(req) error: %s\n", ch->name, zmq_strerror(e));
            goto done;
        }
        if (!running) break;

        /* 3. Receive IQ data from upstream
         *    REQ is now in "recv" state — MUST stay here until we get
         *    the reply or running goes to 0.  Jumping back to step 1
         *    would violate the REQ-REP state machine. */
        int dlen;
        while (running) {
            dlen = zmq_recv(req, buf, MAX_BUF_SIZE, 0);
            if (dlen >= 0) break;
            int e = zmq_errno();
            if (e == EAGAIN || e == EINTR) continue;
            fprintf(stderr, "[%s] recv(req) error: %s\n", ch->name, zmq_strerror(e));
            goto done;
        }
        if (!running) break;

        /* 4. Apply channel impairments to interleaved float32 I/Q samples
         *    Order: (a) estimate original signal power, (b) apply fading,
         *    (c) add AWGN.  Noise power is based on the pre-fading signal
         *    power so that deep fades cause real SNR drops. */
        int nfloats = dlen / (int)sizeof(float);
        if (nfloats >= 2) {
            float *samples = (float *)buf;
            int num_iq = nfloats / 2;

            /* (a) Estimate original signal power (RMS², before fading) */
            float sig_power = 0.0f;
            for (int i = 0; i < nfloats; i++)
                sig_power += samples[i] * samples[i];
            sig_power /= (float)nfloats;

            /* (b) Apply Rayleigh flat fading (complex multiply by h) */
            fading_update(&fading, num_iq, &seed);
            fading_apply(&fading, samples, nfloats);

            if (fading.enabled) {
                float gdb = fading_gain_db(&fading);
                if (msg_count == 0) { min_gain_db = max_gain_db = gdb; }
                if (gdb < min_gain_db) min_gain_db = gdb;
                if (gdb > max_gain_db) max_gain_db = gdb;
            }

            /* (c) Add AWGN (noise floor relative to pre-fading power) */
            if (sig_power > 1e-20f) {
                float noise_std = sqrtf(sig_power / snr_linear);
                float n1, n2;

                /* Process I/Q pairs */
                int i;
                for (i = 0; i + 1 < nfloats; i += 2) {
                    randn_pair(&seed, &n1, &n2);
                    samples[i]     += noise_std * n1;
                    samples[i + 1] += noise_std * n2;
                }
                /* Handle odd trailing float (shouldn't happen with IQ) */
                if (i < nfloats) {
                    randn_pair(&seed, &n1, &n2);
                    samples[i] += noise_std * n1;
                }

                total_samples += (unsigned long)num_iq;
            }
        }

        /* 5. Send impaired IQ data to downstream
         *    REP is in "send" state — retry on EAGAIN/EINTR. */
        while (running) {
            if (zmq_send(rep, buf, dlen, 0) >= 0) break;
            int e = zmq_errno();
            if (e == EAGAIN || e == EINTR) continue;
            fprintf(stderr, "[%s] send(rep) error: %s\n", ch->name, zmq_strerror(e));
            goto done;
        }
        if (!running) break;

        msg_count++;
        if (msg_count % 10000 == 0) {
            if (fading.enabled) {
                printf("[%s] %lu msgs, %.1f M IQ | fade: %.1f..%.1f dB (now %.1f dB)\n",
                       ch->name, msg_count, (double)total_samples / 1e6,
                       min_gain_db, max_gain_db, fading_gain_db(&fading));
            } else {
                printf("[%s] %lu msgs, %.1f M samples processed\n",
                       ch->name, msg_count, (double)total_samples / 1e6);
            }
        }
    }
done:

    free(buf);
    free(req_buf);
    zmq_close(rep);
    zmq_close(req);

    printf("[%s] Stopped after %lu messages\n", ch->name, msg_count);
    return NULL;
}

int main(int argc, char *argv[]) {
    float dl_snr_db   = 10.0f;   /* default: moderate AWGN impairment */
    float ul_snr_db   = 10.0f;
    int   fading      = 0;       /* off by default (backward compatible) */
    float dl_doppler  = 10.0f;   /* Hz — pedestrian speed */
    float ul_doppler  = 10.0f;
    float k_factor_db = 6.0f;    /* default Rician K=6 dB (prevents deep nulls) */
    float srate       = DEFAULT_SRATE;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--dl-snr") == 0 && i + 1 < argc) {
            dl_snr_db = (float)atof(argv[++i]);
        } else if (strcmp(argv[i], "--ul-snr") == 0 && i + 1 < argc) {
            ul_snr_db = (float)atof(argv[++i]);
        } else if (strcmp(argv[i], "--snr") == 0 && i + 1 < argc) {
            dl_snr_db = ul_snr_db = (float)atof(argv[++i]);
        } else if (strcmp(argv[i], "--fading") == 0) {
            fading = 1;
        } else if (strcmp(argv[i], "--doppler") == 0 && i + 1 < argc) {
            dl_doppler = ul_doppler = (float)atof(argv[++i]);
            fading = 1;  /* --doppler implies --fading */
        } else if (strcmp(argv[i], "--dl-doppler") == 0 && i + 1 < argc) {
            dl_doppler = (float)atof(argv[++i]);
            fading = 1;
        } else if (strcmp(argv[i], "--ul-doppler") == 0 && i + 1 < argc) {
            ul_doppler = (float)atof(argv[++i]);
            fading = 1;
        } else if (strcmp(argv[i], "--k-factor") == 0 && i + 1 < argc) {
            k_factor_db = (float)atof(argv[++i]);
        } else if (strcmp(argv[i], "--rayleigh") == 0) {
            k_factor_db = -100.0f;  /* effectively K=0 (pure Rayleigh) */
            fading = 1;
        } else if (strcmp(argv[i], "--srate") == 0 && i + 1 < argc) {
            srate = (float)atof(argv[++i]);
        } else if (strcmp(argv[i], "-h") == 0 || strcmp(argv[i], "--help") == 0) {
            printf("Usage: %s [OPTIONS]\n\n", argv[0]);
            printf("AWGN options:\n");
            printf("  --snr <dB>          Set both DL and UL SNR (default: 10)\n");
            printf("  --dl-snr <dB>       Override DL SNR\n");
            printf("  --ul-snr <dB>       Override UL SNR\n");
            printf("\nFading options:\n");
            printf("  --fading            Enable Rician fading (default K=6 dB)\n");
            printf("  --k-factor <dB>     Rician K-factor in dB (default: 6)\n");
            printf("                       0 dB = equal LoS and scatter (moderate fading)\n");
            printf("                       6 dB = strong LoS, gentle fading (recommended)\n");
            printf("                      10 dB = very gentle fading, nearly AWGN\n");
            printf("  --rayleigh          Pure Rayleigh (K=-inf, deep fades, may crash UE)\n");
            printf("  --doppler <Hz>      Max Doppler frequency, implies --fading (default: 10)\n");
            printf("  --dl-doppler <Hz>   Override DL Doppler, implies --fading\n");
            printf("  --ul-doppler <Hz>   Override UL Doppler, implies --fading\n");
            printf("\nOther:\n");
            printf("  --srate <Hz>        IQ sample rate (default: 23.04e6)\n");
            printf("  -h, --help          Show this help\n");
            printf("\nDoppler guidelines:\n");
            printf("    5 Hz    Stationary / very slow fades\n");
            printf("   10 Hz    Pedestrian   (~3 km/h at 1.8 GHz)\n");
            printf("   70 Hz    Vehicular    (~50 km/h)\n");
            printf("  300 Hz    Highway      (~200 km/h)\n");
            printf("  900 Hz    High-speed train (~600 km/h)\n");
            printf("\nK-factor impact on worst-case fade depth:\n");
            printf("    K=-inf (Rayleigh)   Deep fades to -30 dB (link may drop)\n");
            printf("    K=0 dB              Deep fades to -10 dB\n");
            printf("    K=6 dB              Worst fade ~-3 dB (safe)\n");
            printf("    K=10 dB             Worst fade ~-1 dB (nearly AWGN)\n");
            printf("\nExamples:\n");
            printf("  %s --snr 30 --fading --doppler 5    # Gentle Rician fading (safe)\n", argv[0]);
            printf("  %s --snr 15 --fading --doppler 70   # Vehicular fading\n", argv[0]);
            printf("  %s --snr 10                         # AWGN only (no fading)\n", argv[0]);
            printf("  %s --rayleigh --doppler 10 --snr 30 # Aggressive Rayleigh (may crash UE)\n", argv[0]);
            return 0;
        }
    }

    /* ── Banner ──────────────────────────────────────────────────────────── */
    printf("╔═════════════════════════════════════════════════════════╗\n");
    if (fading) {
        if (k_factor_db > -50.0f)
            printf("║     ZMQ Channel Broker  (AWGN + Rician Fading)       ║\n");
        else
            printf("║     ZMQ Channel Broker  (AWGN + Rayleigh Fading)     ║\n");
    } else {
        printf("║     ZMQ Channel Broker  (AWGN only)                   ║\n");
    }
    printf("╠═════════════════════════════════════════════════════════╣\n");
    if (fading) {
        printf("║  DL: SNR %5.1f dB  Doppler %4.0f Hz  K=%5.1f dB     ║\n", dl_snr_db, dl_doppler, k_factor_db);
        printf("║  UL: SNR %5.1f dB  Doppler %4.0f Hz  K=%5.1f dB     ║\n", ul_snr_db, ul_doppler, k_factor_db);
    } else {
        printf("║  DL: SNR %5.1f dB                                     ║\n", dl_snr_db);
        printf("║  UL: SNR %5.1f dB                                     ║\n", ul_snr_db);
    }
    printf("╠═════════════════════════════════════════════════════════╣\n");
    printf("║  gNB TX :4000 → [channel] → :2000 → UE RX              ║\n");
    printf("║  UE  TX :2001 → [channel] → :4001 → gNB RX             ║\n");
    printf("╚═════════════════════════════════════════════════════════╝\n\n");

    signal(SIGINT,  sig_handler);
    signal(SIGTERM, sig_handler);
    signal(SIGPIPE, SIG_IGN);

    void *ctx = zmq_ctx_new();

    channel_args_t dl_args = {
        .name             = "DL",
        .rep_bind_addr    = "tcp://127.0.0.1:2000",   /* UE connects here */
        .req_connect_addr = "tcp://127.0.0.1:4000",   /* gNB binds here   */
        .snr_db           = dl_snr_db,
        .fading_enabled   = fading,
        .doppler_hz       = dl_doppler,
        .sample_rate      = srate,
        .zmq_ctx          = ctx,
        .rng_seed         = (unsigned int)time(NULL) ^ 0xDEAD,
        .k_factor_db      = k_factor_db
    };

    channel_args_t ul_args = {
        .name             = "UL",
        .rep_bind_addr    = "tcp://127.0.0.1:4001",   /* gNB connects here */
        .req_connect_addr = "tcp://127.0.0.1:2001",   /* UE binds here     */
        .snr_db           = ul_snr_db,
        .fading_enabled   = fading,
        .doppler_hz       = ul_doppler,
        .sample_rate      = srate,
        .zmq_ctx          = ctx,
        .rng_seed         = (unsigned int)time(NULL) ^ 0xBEEF,
        .k_factor_db      = k_factor_db
    };

    pthread_t dl_thread, ul_thread;
    pthread_create(&dl_thread, NULL, channel_thread, &dl_args);
    pthread_create(&ul_thread, NULL, channel_thread, &ul_args);

    printf("Broker running — Ctrl+C to stop\n\n");

    pthread_join(dl_thread, NULL);
    pthread_join(ul_thread, NULL);

    zmq_ctx_destroy(ctx);
    printf("\nBroker shut down.\n");
    return 0;
}
