import os
import re
import subprocess
import random
import numpy as np

# ============================================================
# Configuracao geral
# ============================================================
circuit_name = "rf_lna"
f0 = 2.4e9          
vdd = 1.8
Zo = 50
temperature_c = 27
temperature_k = temperature_c + 273.15
k_boltzmann = 1.380649e-23
mos_model = "sky130_fd_pr__nfet_01v8"   

def parse_measures(stdout_text):
    measures = {}
    pattern = re.compile(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", re.MULTILINE)

    for match in pattern.finditer(stdout_text):
        name = match.group(1).strip().lower()
        value = float(match.group(2))
        measures[name] = value
    return measures

def simulate():
    cmd = ["ngspice", "-b", f"./{circuit_name}.cir"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    measures = parse_measures(result.stdout)

    required_measures = {
        "gain_db",
        "f_3db_low",
        "f_3db_high",
        "vin_re",
        "vin_im",
        "iin_re",
        "iin_im",
        "out_noise",
        "in_noise",
        "inoise_total",
        "onoise_total",
        "idd",
        "pdc"
    }

    if result.returncode != 0 and not required_measures.issubset(measures):
        print("Erro no ngspice:")
        print(result.stderr)
        print(result.stdout)
        raise RuntimeError("Falha na simulacao.")

    if not required_measures.issubset(measures):
        print("Stdout do ngspice:")
        print(result.stdout)
        missing = sorted(required_measures - set(measures))
        raise RuntimeError("Medidas ausentes no stdout do ngspice: %s" % missing)

    return measures


def write_netlist(x):
    """
    x[0] = Vg   (V)
    x[1] = W    (um)
    x[2] = length (um)
    x[3] = Lg   (H)
    x[4] = Ls   (H)
    x[5] = Ld   (H)
    """

    vg = x[0]
    w  = x[1]
    L  = x[2]
    lg = x[3]
    ls = x[4]
    ld = x[5]

    netlist_file = f"{circuit_name}.cir"

    with open(netlist_file, "w") as fp:
        fp.write("* RF LNA - Common Source with Inductive Degeneration\n")
        fp.write(".lib \"$PDK_ROOT/sky130A/libs.tech/combined/sky130.lib.spice\" tt\n\n")

        fp.write(f".options temp={temperature_c}\n")
        fp.write(f".param F0={f0}\n")
        fp.write(f".csparam f0={f0}\n")
        fp.write(f".param VDD={vdd}\n")
        fp.write(f".param VG={vg}\n")
        fp.write(f".param WNMOS={w}\n")
        fp.write(f".param LNMOS={L}\n")
        fp.write(f".param LG={lg}\n")
        fp.write(f".param LS={ls}\n")
        fp.write(f".param LD={ld}\n\n")

        fp.write("VDD vdd 0 DC {VDD}\n")
        fp.write("VBIAS vbias 0 DC {VG}\n\n")

        fp.write("VIN       src 0 AC 1 DC 0\n")
        fp.write("Rsource   src in %s\n" % Zo)
        fp.write("CIN       in p1 1p\n")

        fp.write("LGATE p1 gate {LG}\n")
        fp.write("RBIAS gate vbias 1MEG\n")   # bias sem carregar muito o AC

        fp.write("LSRC source 0 {LS}\n")
        fp.write("xn1 drain gate source 0 %s l={LNMOS} w={WNMOS}\n" % mos_model)

        fp.write("LLOAD vdd drain {LD}\n")

        fp.write("COUT drain out 1p\n")
        fp.write("RLOAD out 0 %s\n\n" % Zo)

        # Medidas
        fp.write(".control\n")
        fp.write("set sqrnoise\n")
        fp.write("op\n")
        fp.write("let idd = -i(VDD)\n")
        fp.write("let pdc = v(vdd) * idd\n")
        fp.write("echo idd = \"$&idd\"\n")
        fp.write("echo pdc = \"$&pdc\"\n")
        
        fp.write("ac dec 200 100MEG 10G\n\n")

        #fp.write("run\n")
        fp.write("setplot ac1\n")
        fp.write("let gain_db_vector = db(v(out)/v(in))\n")
        fp.write("meas ac gain_db       find    gain_db_vector                at=%s\n" % f0)

        fp.write("let gain_3db = gain_db - 3\n")
        fp.write("meas ac f_3db_low    when    gain_db_vector=gain_3db      rise=1\n")
        fp.write("meas ac f_3db_high   when    gain_db_vector=gain_3db      fall=1\n")
        fp.write("if (f_3db_low eq 0)\n")
        fp.write("  let f_3db_low = 100MEG\n")
        fp.write("end\n")
        fp.write("if (f_3db_high eq 0)\n")
        fp.write("  let f_3db_high = 10G\n")
        fp.write("end\n")
        fp.write("noise v(out) VIN dec 200 $&f_3db_low $&f_3db_high\n\n")

        fp.write("setplot ac1\n")

        fp.write("let vin_re_vector = real(v(in))\n")
        fp.write("meas ac vin_re       find    vin_re_vector                     at=%s\n" % f0)

        fp.write("let vin_im_vector = imag(v(in))\n")
        fp.write("meas ac vin_im       find    vin_im_vector                     at=%s\n" % f0)

        fp.write("let iin_re_vector = real(i(VIN))\n")
        fp.write("meas ac iin_re       find    iin_re_vector                  at=%s\n" % f0)

        fp.write("let iin_im_vector = imag(i(VIN))\n")
        fp.write("meas ac iin_im       find    iin_im_vector                    at=%s\n" % f0)

        fp.write("let vout_re_vector = real(v(out))\n")
        fp.write("meas ac vout_re      find    vout_re_vector                    at=%s\n" % f0)

        fp.write("let vout_im_vector = imag(v(out))\n")
        fp.write("meas ac vout_im      find    vout_im_vector                    at=%s\n" % f0)

        fp.write("setplot noise1\n")
        fp.write("let nn = 0\n")
        fp.write("while frequency[nn] < f0\n")
        fp.write("  let nn = nn +1\n")
        fp.write("end\n")
        fp.write("let fnn = frequency[nn]\n")
        fp.write("let nn1 = nn -1\n")
        fp.write("let fnn1 = frequency[nn1]\n")
        fp.write("let onn = onoise_spectrum[nn]\n")
        fp.write("let onn1 = onoise_spectrum[nn1]\n")
        fp.write("let onoise = onn1 +(f0 - fnn1)*(onn - onn1)/(fnn - fnn1)\n")
        fp.write("echo out_noise \t\t\t\t\t\t= \"$&onoise\"\n")
        fp.write("let inn = inoise_spectrum[nn]\n")
        fp.write("let inn1 = inoise_spectrum[nn1]\n")
        fp.write("let inoise = inn1 +(f0 - fnn1)*(inn - inn1)/(fnn - fnn1)\n")
        fp.write("echo in_noise \t\t\t\t\t\t= \"$&inoise\"\n")
    
        fp.write("setplot noise2\n")
        fp.write("print inoise_total\n")
        fp.write("print onoise_total\n")

        fp.write(".endc\n")
        
        fp.write(".end\n")


def evaluate_lna(measures):
    gain_db     = measures.get("gain_db",       -1e9)
    f_3db_low   = measures.get("f_3db_low",     0)
    f_3db_high  = measures.get("f_3db_high",    0)
    vin_re      = measures.get("vin_re",        1e9)
    vin_im      = measures.get("vin_im",        1e9)
    iin_re      = measures.get("iin_re",        1e9)
    iin_im      = measures.get("iin_im",        1e9)
    vout_re     = measures.get("vout_re",       -1e9)
    vout_im     = measures.get("vout_im",       -1e9)
    out_noise   = measures.get("out_noise",     1e9)
    in_noise    = measures.get("in_noise",      1e9)
    inoise_total= measures.get("inoise_total",  0)
    onoise_total= measures.get("onoise_total",  1e9)
    idd         = measures.get("idd",           1e9)
    pdc         = measures.get("pdc",           1e9)

    band_width  = f_3db_high - f_3db_low                    #BW
    f_bw        = 100*band_width/f0                         #BW normalized by target freq

    vin         = complex(vin_re, vin_im)                   #Input Voltage ahead Rsource
    iin         = -complex(iin_re, iin_im)                   #Input current
    zin         = vin/iin                                   #Input Impedance

    vout        = complex(vout_re, vout_im)                 #Output Voltage

    gamma       = (zin - Zo) / (zin + Zo)                   #Reflection Coefficient
    s11_mag     = abs(gamma)                                 
    s11_db      = 20 * np.log10(s11_mag)

    NF          = inoise_total/(4*k_boltzmann*temperature_k*Zo*band_width)
    NF_db       = 10 * np.log10(NF)

    return {
        "gain_db":        gain_db,
        "f_band_width":   f_bw,
        "s11_db":         s11_db,
        "NF_db":          NF_db
    }


def costfun_lna(x):
    write_netlist(x)
    measures = simulate()
    metrics = evaluate_lna(measures)

    gain_db     = metrics["gain_db"]
    fbw         = metrics["f_band_width"]
    s11_db      = metrics["s11_db"]
    NF_db       = metrics["NF_db"]
    
    target_fbw    = 1
    target_s11_db = -10
    target_NF_db  = 2
    target_gain   = 5

    penalty_fbw = max(0.0, fbw - target_fbw) ** 2
    penalty_s11 = max(0.0, s11_db - target_s11_db) ** 2
    penalty_NF  = max(0.0, NF_db - target_NF_db) ** 2
    penalty_gain= max(0.0, gain_db - target_gain) ** 2

    weigth_fbw  = -10
    weigth_s11  = 10
    weigth_NF   = 100
    weigth_gain = -10
    cost = (
        + weigth_fbw  * penalty_fbw
        + weigth_s11  * penalty_s11
        + weigth_NF   * penalty_NF
        + weigth_gain * penalty_gain
    )

    print("x = %s \t| gain = %.2f dB \t| FBW = %.2f %% \t| S11 = %.2f dB \t| NF = %.2f dB \t| cost = %.4f"
        % (
            np.array2string(x, precision=4, suppress_small=False),
            gain_db,
            fbw,
            s11_db,
            NF_db,
            cost
        )
    )

    return cost, metrics


def hill_climbing_randn(x0, boundaries, max_no_improve=400, sigma=0.15):
    x = np.copy(x0)
    cost, metrics = costfun_lna(x)

    best_x = np.copy(x)
    best_cost = cost
    best_metrics = metrics

    history = []
    iter_count = 0
    iter_without_gain = 0

    while iter_without_gain < max_no_improve:
        idx = random.randint(0, len(x) - 1)

        x_candidate = np.copy(x)
        step = sigma * x_candidate[idx] * np.random.randn()

        # Se o parametro for muito pequeno, evita passo nulo
        if abs(x_candidate[idx]) < 1e-15:
            step = sigma * np.random.randn()

        x_candidate[idx] = x_candidate[idx] + step

        # Aplica limites
        x_candidate = np.maximum(x_candidate, boundaries[:, 0])
        x_candidate = np.minimum(x_candidate, boundaries[:, 1])

        try:
            cost_candidate, metrics_candidate = costfun_lna(x_candidate)
        except Exception as e:
            print(f"Falha no candidato: {e}")
            iter_without_gain += 1
            iter_count += 1
            continue

        if cost_candidate < cost:
            x = x_candidate
            cost = cost_candidate
            metrics = metrics_candidate
            iter_without_gain = 0
            history.append((np.copy(x), cost, metrics.copy()))

            if cost < best_cost:
                best_x = np.copy(x)
                best_cost = cost
                best_metrics = metrics.copy()

            print(">>> melhoria aceita")
        else:
            iter_without_gain += 1

        iter_count += 1

    return best_x, best_cost, best_metrics, history


# x = [Vg, W, Lg, Ls, Ld]
x0 = np.array([
    0.75,      # Vg [V]
    100,       # W  [um]
    0.15,      # L  [um]
    8e-9,      # Lg [H]
    1.5e-9,    # Ls [H]
    6e-9       # Ld [H]
], dtype=float)

boundaries = np.array([
    [0.45,   1.50],     # Vg
    [2,  1000],         # W
    [0.15, 1],          # L
    [0.5e-9, 20e-9],    # Lg
    [0.1e-9, 10e-9],    # Ls
    [0.5e-9, 20e-9],    # Ld
], dtype=float)

best_x, best_cost, best_metrics, history = hill_climbing_randn(
    x0=x0,
    boundaries=boundaries,
    max_no_improve=300,
    sigma=0.20
)

print("\n================ FINAL RESULT ================\n")
print("Best x found:")
print("Vg = %.4f V" % best_x[0])
print("W  = %.3f um" % best_x[1])
print("L  = %.3f um" % best_x[2])
print("Lg = %.3e H" % best_x[3])
print("Ls = %.3e H" % best_x[4])
print("Ld = %.3e H" % best_x[5])
print("Cost = %.5f" % best_cost)

print("\nFinal achivements:")
print("Gain  = %.2f dB" % best_metrics["gain_db"])
print("FBW   = %.2f %"  % best_metrics["f_band_width"])
print("S11   = %.2f dB" % best_metrics["s11_db"])
print("NF    = %.2f dB" % best_metrics["NF_db"])
 
