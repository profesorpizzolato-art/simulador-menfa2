"""
Simulador Integral MENFA - basado en el Manual Maestro de Perforacion 3.0
Modulos:
  1. Hidraulica y mecanica de sarta (FF, Hook Load, BHP, ECD, Punto Neutro)
  2. Control de pozos (KMW, ICP, FCP, MAASP, influjo, tabla de presiones)
  3. Perforacion direccional (Rotacion / Deslizando, Toolface, DLS)
  4. Escenarios de control (kick perforando, kick en viaje con Trip Tank, gas migratorio)
     con dibujo del equipo y de la sala de control
  5. Manual Maestro (consultas y guía del usuario)

Uso standalone: streamlit run simulador_menfa.py
Uso desde app.py: from simulador_menfa import mostrar_simulador; mostrar_simulador()
"""
import math
import random

import pandas as pd
import streamlit as st

# ----------------------------------------------------------------------------
# FORMULAS (todas tomadas del manual; unidades de campo: ppg, ft, psi, bbl)
# ----------------------------------------------------------------------------
def factor_flotacion(mw):
    return (65.5 - mw) / 65.5


def bhp(mw, tvd):
    return 0.052 * mw * tvd


def kmw(sidpp, tvd, mw):
    return sidpp / (0.052 * tvd) + mw


def maasp(emw_fractura, mw, tvd_zapato):
    return 0.052 * (emw_fractura - mw) * tvd_zapato


def desplazar_survey(inc1, az1, inc2, az2, dmd):
    """Metodo de curvatura minima. Angulos en grados, dmd en metros."""
    i1, i2 = math.radians(inc1), math.radians(inc2)
    a1, a2 = math.radians(az1), math.radians(az2)
    cos_b = math.cos(i1) * math.cos(i2) + math.sin(i1) * math.sin(i2) * math.cos(a2 - a1)
    beta = math.acos(max(-1.0, min(1.0, cos_b)))
    rf = 1.0 if beta < 1e-9 else (2 / beta) * math.tan(beta / 2)
    dn = dmd / 2 * (math.sin(i1) * math.cos(a1) + math.sin(i2) * math.cos(a2)) * rf
    de = dmd / 2 * (math.sin(i1) * math.sin(a1) + math.sin(i2) * math.sin(a2)) * rf
    dtvd = dmd / 2 * (math.cos(i1) + math.cos(i2)) * rf
    dls = math.degrees(beta) / dmd * 30 if dmd else 0.0
    return dn, de, dtvd, dls


# ----------------------------------------------------------------------------
# MODULO 1: HIDRAULICA Y SARTA
# ----------------------------------------------------------------------------
def modulo_hidraulica():
    st.subheader("Hidráulica y mecánica de la sarta")
    c1, c2 = st.columns(2)
    with c1:
        mw = st.number_input("Densidad del lodo (ppg)", 8.0, 20.0, 10.0, 0.1, key="h_mw")
        tvd = st.number_input("TVD (ft)", 500.0, 30000.0, 8000.0, 100.0, key="h_tvd")
        pore = st.number_input("Presión de poros (psi)", 0.0, 20000.0, 3900.0, 50.0, key="h_pore")
        frac = st.number_input("Presión de fractura (psi)", 0.0, 25000.0, 5800.0, 50.0, key="h_frac")
        dp_ann = st.number_input("Pérdida de presión anular (psi)", 0.0, 2000.0, 120.0, 10.0, key="h_dp")
    with c2:
        peso_aire = st.number_input("Peso de la sarta en aire (lb)", 10000.0, 800000.0, 180000.0, 1000.0, key="h_pa")
        wob = st.number_input("WOB (lb)", 0.0, 80000.0, 20000.0, 1000.0, key="h_wob")
        bombas = st.toggle("Bombas encendidas", value=True, key="h_bomb")
        dc_peso = st.number_input("Peso unitario portamechas (lb/ft)", 20.0, 300.0, 83.0, 1.0, key="h_dcw")
        dc_long = st.number_input("Longitud de portamechas (ft)", 0.0, 2000.0, 300.0, 10.0, key="h_dcl")

    ff = factor_flotacion(mw)
    hook = peso_aire * ff - wob
    ecd = mw + (dp_ann / (0.052 * tvd) if bombas else 0.0)
    bhp_est = bhp(mw, tvd)
    bhp_din = bhp(ecd, tvd)
    overbalance = bhp_din - pore
    punto_neutro = wob / (dc_peso * ff)

    m = st.columns(4)
    m[0].metric("Factor de flotación", f"{ff:.3f}")
    m[1].metric("Hook Load (lb)", f"{hook:,.0f}")
    m[2].metric("ECD (ppg)", f"{ecd:.2f}")
    m[3].metric("Overbalance (psi)", f"{overbalance:,.0f}")
    m = st.columns(3)
    m[0].metric("BHP estática (psi)", f"{bhp_est:,.0f}")
    m[1].metric("BHP dinámica (psi)", f"{bhp_din:,.0f}")
    m[2].metric("Punto neutro (ft sobre mecha)", f"{punto_neutro:,.0f}")

    if bhp_din <= pore:
        st.error("BHP por debajo de la presión de poros: riesgo de KICK. Hacer Flow Check.")
    elif bhp_din >= frac:
        st.error("BHP supera la presión de fractura: riesgo de pérdida de circulación.")
    else:
        st.success("BHP entre presión de poros y fractura: barrera primaria íntegra.")
    if punto_neutro > dc_long:
        st.warning("El punto neutro cae fuera de los portamechas: la tubería delgada trabaja en compresión.")
    if not bombas and bhp_est <= pore:
        st.warning("Con bombas apagadas se pierde el ECD: la hidrostática sola no alcanza.")


# ----------------------------------------------------------------------------
# MODULO 2: CONTROL DE POZOS
# ----------------------------------------------------------------------------
def modulo_control():
    st.subheader("Control de pozos")
    c1, c2 = st.columns(2)
    with c1:
        mw = st.number_input("Densidad actual (ppg)", 8.0, 20.0, 10.0, 0.1, key="c_mw")
        tvd = st.number_input("TVD (ft)", 500.0, 30000.0, 8000.0, 100.0, key="c_tvd")
        sidpp = st.number_input("SIDPP (psi)", 0.0, 3000.0, 400.0, 10.0, key="c_sidpp")
        sicp = st.number_input("SICP (psi)", 0.0, 4000.0, 550.0, 10.0, key="c_sicp")
        scr = st.number_input("SCR - presión a caudal reducido (psi)", 0.0, 3000.0, 600.0, 10.0, key="c_scr")
    with c2:
        pit_gain = st.number_input("Pit Gain (bbl)", 0.0, 200.0, 15.0, 1.0, key="c_pg")
        cap_anular = st.number_input("Capacidad anular en portamechas (bbl/ft)", 0.005, 0.2, 0.0292, 0.001,
                                     format="%.4f", key="c_cap")
        tvd_zapato = st.number_input("TVD del zapato (ft)", 500.0, 20000.0, 5000.0, 100.0, key="c_tz")
        emw_frac = st.number_input("Densidad equivalente de fractura (ppg)", 8.0, 25.0, 15.0, 0.1, key="c_emw")
        emb_sup_mecha = st.number_input("Emboladas superficie-mecha", 100, 20000, 2400, 100, key="c_strk")

    k = kmw(sidpp, tvd, mw)
    icp = sidpp + scr
    fcp = scr * (k / mw)
    maasp_act = maasp(emw_frac, mw, tvd_zapato)
    altura = pit_gain / cap_anular
    grad_influjo = 0.052 * mw - (sicp - sidpp) / altura if altura else 0.0

    if grad_influjo < 0.25:
        tipo = "gas"
    elif grad_influjo < 0.40:
        tipo = "petróleo o mezcla"
    else:
        tipo = "agua salada"

    m = st.columns(4)
    m[0].metric("KMW (ppg)", f"{k:.2f}")
    m[1].metric("ICP (psi)", f"{icp:,.0f}")
    m[2].metric("FCP (psi)", f"{fcp:,.0f}")
    m[3].metric("MAASP (psi)", f"{maasp_act:,.0f}")
    m = st.columns(2)
    m[0].metric("Altura del influjo (ft)", f"{altura:,.0f}")
    m[1].metric("Gradiente del influjo (psi/ft)", f"{grad_influjo:.3f}", tipo)

    if pit_gain > 5:
        st.error("Pit Gain > 5 bbl: alarma crítica. Flow Check y, si fluye, cierre duro.")
    if sicp > maasp_act:
        st.error("SICP supera la MAASP: riesgo de fracturar el zapato.")
    if sicp < sidpp:
        st.warning("SICP menor que SIDPP: revisar lecturas (válvula flotadora o presión atrapada).")

    st.markdown("**Tabla de presiones de circulación (Método Esperar y Pesar)**")
    pasos = 10
    filas = [{"Emboladas": round(emb_sup_mecha * i / pasos),
              "Presión (psi)": round(icp - (icp - fcp) * i / pasos)} for i in range(pasos + 1)]
    df = pd.DataFrame(filas)
    st.line_chart(df, x="Emboladas", y="Presión (psi)")
    st.dataframe(df, hide_index=True, use_container_width=True)


# ----------------------------------------------------------------------------
# MODULO 3: PERFORACION DIRECCIONAL
# ----------------------------------------------------------------------------
def _reiniciar_survey():
    st.session_state.survey = [{"MD": 0.0, "Inc": 2.0, "Az": 90.0, "TVD": 0.0,
                                "N": 0.0, "E": 0.0, "DLS": 0.0, "Modo": "Inicio"}]


def modulo_direccional():
    st.subheader("Perforación direccional")
    if "survey" not in st.session_state:
        _reiniciar_survey()

    c1, c2, c3, c4 = st.columns(4)
    modo = c1.radio("Modo", ["Rotación", "Deslizando"], key="d_modo")
    dmd = c2.number_input("Tramo a perforar (m)", 1.0, 100.0, 10.0, 1.0, key="d_dmd")
    dls_set = c3.number_input("DLS del motor (°/30 m)", 0.0, 12.0, 4.0, 0.5, key="d_dls",
                              disabled=(modo == "Rotación"))
    tf = c4.number_input("Toolface (°)", 0, 359, 0, 5, key="d_tf", disabled=(modo == "Rotación"))

    b1, b2 = st.columns(2)
    if b1.button("Perforar tramo", type="primary", use_container_width=True):
        ult = st.session_state.survey[-1]
        inc, az = ult["Inc"], ult["Az"]
        if modo == "Deslizando":
            delta = dls_set / 30.0 * dmd  # Delta Angulo = (DLS_set / 30) x Delta Profundidad
            tfr = math.radians(tf)
            inc_n = min(max(inc + delta * math.cos(tfr), 0.0), 180.0)
            az_n = (az + delta * math.sin(tfr) / max(math.sin(math.radians(inc)), 0.05)) % 360
        else:
            inc_n, az_n = inc, az  # RPM > 0: el pozo mantiene rumbo (sin deriva modelada)
        dn, de, dtvd, dls_real = desplazar_survey(inc, az, inc_n, az_n, dmd)
        st.session_state.survey.append({
            "MD": ult["MD"] + dmd, "Inc": round(inc_n, 2), "Az": round(az_n, 2),
            "TVD": ult["TVD"] + dtvd, "N": ult["N"] + dn, "E": ult["E"] + de,
            "DLS": round(dls_real, 2), "Modo": modo})
        if dls_real > 4.0:
            st.warning("DLS > 4.0: curva agresiva. Aumenta torque, drag y riesgo de Keyseating.")
    if b2.button("Reiniciar pozo", use_container_width=True):
        _reiniciar_survey()
        st.rerun()

    df = pd.DataFrame(st.session_state.survey)
    ult = df.iloc[-1]
    m = st.columns(4)
    m[0].metric("MD (m)", f"{ult['MD']:.0f}")
    m[1].metric("TVD (m)", f"{ult['TVD']:.1f}")
    m[2].metric("Inclinación (°)", f"{ult['Inc']:.1f}")
    m[3].metric("Azimut (°)", f"{ult['Az']:.1f}")

    g1, g2 = st.columns(2)
    with g1:
        st.caption("Perfil vertical (desplazamiento horizontal vs profundidad)")
        perfil = pd.DataFrame({"Desplazamiento (m)": (df["N"] ** 2 + df["E"] ** 2) ** 0.5,
                               "Profundidad (-TVD)": -df["TVD"]})
        st.line_chart(perfil, x="Desplazamiento (m)", y="Profundidad (-TVD)")
    with g2:
        st.caption("Vista en planta (Norte vs Este)")
        st.line_chart(df, x="E", y="N")

    with st.expander("Ver tabla de estaciones"):
        st.dataframe(df.round(2), hide_index=True, use_container_width=True)
    st.info("Toolface 0° = sube ángulo (Build) · 180° = baja ángulo (Drop) · 90° / 270° = gira el azimut.")


# ----------------------------------------------------------------------------
# MODULO 4: ESCENARIOS DE CONTROL DE POZO (con equipo y sala de control)
# ----------------------------------------------------------------------------
def _gauge(cx, cy, g):
    valor, vmax, etiqueta, unidad = g
    ang = -120 + 240 * min(max(valor / vmax, 0), 1)
    return (
        f'<circle cx="{cx}" cy="{cy}" r="46" fill="#10161d" stroke="#5b6b7c" stroke-width="3"/>'
        f'<line x1="{cx}" y1="{cy}" x2="{cx}" y2="{cy-38}" stroke="#ffb020" stroke-width="3" '
        f'transform="rotate({ang:.0f} {cx} {cy})"/>'
        f'<circle cx="{cx}" cy="{cy}" r="4" fill="#ffb020"/>'
        f'<text x="{cx}" y="{cy+32}" font-size="11" fill="#9fb3c8" text-anchor="middle">{valor:,.1f} {unidad}</text>'
        f'<text x="{cx}" y="{cy+66}" font-size="12" fill="#e6edf3" text-anchor="middle">{etiqueta}</text>')


def _sala_control(g1, g2, g3, cerrado, alarma):
    """Dibujo del equipo (torre + BOP) y de la consola del perforador, con manometros vivos."""
    bop = "#e5484d" if cerrado else "#2e7d32"
    led = "#e5484d" if alarma else "#2e7d32"
    return (
        '<svg viewBox="0 0 700 260" xmlns="http://www.w3.org/2000/svg" font-family="sans-serif">'
        '<rect width="700" height="260" rx="10" fill="#0b1117"/>'
        '<rect x="0" y="228" width="250" height="32" fill="#2a2f36"/>'
        '<polygon points="95,228 125,40 155,40 185,228" fill="none" stroke="#8aa0b4" stroke-width="3"/>'
        '<line x1="103" y1="170" x2="177" y2="170" stroke="#8aa0b4" stroke-width="2"/>'
        '<line x1="111" y1="115" x2="169" y2="115" stroke="#8aa0b4" stroke-width="2"/>'
        '<line x1="103" y1="170" x2="169" y2="115" stroke="#8aa0b4" stroke-width="2"/>'
        '<line x1="177" y1="170" x2="111" y2="115" stroke="#8aa0b4" stroke-width="2"/>'
        '<rect x="115" y="30" width="50" height="12" fill="#5b6b7c"/>'
        '<line x1="140" y1="42" x2="140" y2="90" stroke="#c9d4df" stroke-width="2"/>'
        '<rect x="128" y="90" width="24" height="26" fill="#ffb020"/>'
        '<line x1="140" y1="116" x2="140" y2="228" stroke="#c9d4df" stroke-width="5"/>'
        f'<rect x="105" y="196" width="70" height="32" rx="4" fill="{bop}"/>'
        f'<text x="140" y="248" font-size="12" fill="#e6edf3" text-anchor="middle">'
        f'BOP {"CERRADO" if cerrado else "ABIERTO"}</text>'
        '<rect x="270" y="20" width="410" height="220" rx="12" fill="#1a232d" stroke="#3a4a5c"/>'
        '<text x="290" y="46" font-size="13" fill="#e6edf3">SALA DE CONTROL · CONSOLA DEL PERFORADOR</text>'
        f'<circle cx="650" cy="41" r="9" fill="{led}"/>'
        + _gauge(345, 125, g1) + _gauge(475, 125, g2) + _gauge(605, 125, g3) +
        '</svg>')


ACC_PERF = ["Seguir perforando", "Realizar Flow Check",
            "Espaciar la sarta (tool joint fuera de los arietes)",
            "Parar bombas y frenar la mesa rotaria", "Cerrar el BOP y abrir la HCR",
            "Registrar SIDPP y SICP (5 a 10 min)", "Circular para limpiar el pozo"]
ACC_VIAJE = ["Sacar 5 tiros", "Realizar Flow Check",
             "Espaciar la sarta (tool joint fuera de los arietes)",
             "Conectar y cerrar la válvula TIW", "Cerrar el BOP y abrir la HCR",
             "Registrar SICP y SIDPP (5 a 10 min)", "Seguir sacando a mayor velocidad"]
ACC_GAS = ["Esperar 15 min y registrar presiones", "Purgar un pequeño volumen de lodo por el choke",
           "Desviar el flujo al separador de gas (Pobre Boy)", "Abrir el pozo por completo"]


def _avanzar_perf(e):
    e["pit"] += random.choice([1.5, 2.0, 2.5])
    return f"Perforás 1 minuto más. Pit Gain: {e['pit']:.1f} bbl."


def _avanzar_viaje(e):
    e["tiros"] += 5
    ganancia = random.choice([0.8, 1.0, 1.2]) if e["tiros"] > e["onset"] else 0.0
    e["pit"] += ganancia
    e["tabla"].append({"Tiros": e["tiros"], "Esperado (bbl)": 4.5, "Real (bbl)": round(4.5 - ganancia, 1),
                       "Déficit acum. (bbl)": round(e["pit"], 1)})
    return f"Sacás 5 tiros (total {e['tiros']}). Revisá la hoja del Trip Tank."


CFG = {
    "Kick perforando": dict(
        acciones=ACC_PERF, umbral=5.0, penal=3.0, avanzar=_avanzar_perf, etq="Pit Gain",
        alarma="ALARMA: Pit Gain > 5 bbl. Decidí qué hacer.",
        presion=lambda e: 2500 if e["paso"] <= 1 else (e["sicp"] if e["paso"] >= 4 else 0),
        g3=lambda e: (152.0, 300, "Hook Load", "klb")),
    "Kick en viaje (Trip Tank)": dict(
        acciones=ACC_VIAJE, umbral=1.0, penal=1.0, avanzar=_avanzar_viaje, etq="Déficit Trip Tank",
        alarma="ALARMA: el pozo toma menos lodo que el acero extraído. Posible surgencia.",
        presion=lambda e: e["sicp"] if e["paso"] >= 4 else 0,
        g3=lambda e: (e["tiros"], 30, "Tiros sacados", "")),
}


def _nuevo(tipo):
    sidpp = random.randrange(250, 601, 10)
    st.session_state.esc = {
        "tipo": tipo, "mw": 10.0, "tvd": 8000.0, "sidpp": sidpp,
        "sicp": sidpp + random.randrange(80, 201, 10), "pit": 0.0, "paso": 0, "errores": 0,
        "fin": False, "tiros": 0, "onset": random.randrange(6, 16), "tabla": [],
        "log": ["Operación normal. Monitoreá las piletas / el Trip Tank."]}


def _ejecutar(accion, cfg):
    e = st.session_state.esc
    if e["fin"]:
        return
    ac = cfg["acciones"]
    if accion == ac[0]:
        if e["paso"] == 0:
            e["log"].append(cfg["avanzar"](e))
        else:
            e["errores"] += 1
            e["pit"] += cfg["penal"]
            e["log"].append("Error: seguir con la maniobra con el pozo comprometido agranda el influjo.")
        return
    if accion == ac[1:6][e["paso"]]:
        if e["paso"] == 0 and e["pit"] <= cfg["umbral"]:
            e["log"].append("Flow Check sin indicios: no hay surgencia confirmada. Seguí monitoreando.")
            return
        e["paso"] += 1
        e["log"].append("Correcto: " + accion)
        e["fin"] = e["paso"] == 5
    else:
        e["errores"] += 1
        if e["paso"] < 4:  # antes de cerrar el pozo el influjo sigue entrando
            e["pit"] += cfg["penal"]
        e["log"].append("Error: esa acción no corresponde ahora. Revisá el protocolo de Cierre Duro.")


def _escenario_kick(tipo):
    cfg = CFG[tipo]
    if st.session_state.get("esc", {}).get("tipo") != tipo:
        _nuevo(tipo)
    e = st.session_state.esc
    alarma = e["pit"] > cfg["umbral"] and not e["fin"]
    st.image(_sala_control((e["pit"], 15, cfg["etq"], "bbl"), (cfg["presion"](e), 3000, "Presión", "psi"),
                           cfg["g3"](e), e["paso"] >= 4, alarma), use_container_width=True)
    m = st.columns(3)
    m[0].metric(cfg["etq"] + " (bbl)", f"{e['pit']:.1f}")
    m[1].metric("Pasos correctos", f"{e['paso']} / 5")
    m[2].metric("Errores", e["errores"])
    st.progress(e["paso"] / 5)
    if alarma:
        st.error(cfg["alarma"])
    if not e["fin"]:
        k = f"esc_accion_{tipo}"
        st.selectbox("Acción del perforador", cfg["acciones"], key=k)
        st.button("Ejecutar acción", type="primary", on_click=lambda: _ejecutar(st.session_state[k], cfg))
    if e["tabla"]:
        st.markdown("**Hoja del Trip Tank**")
        st.dataframe(pd.DataFrame(e["tabla"]), hide_index=True, use_container_width=True)
    st.markdown("**Bitácora**")
    for linea in reversed(e["log"][-8:]):
        st.write("• " + linea)
    if e["fin"]:
        puntaje = max(0, round(100 - 15 * e["errores"] - 3 * max(0.0, e["pit"] - 8)))
        st.success(f"Pozo cerrado. Puntaje: {puntaje} / 100.")
        st.write(f"Presiones estabilizadas: SIDPP = {e['sidpp']} psi · SICP = {e['sicp']} psi "
                 f"(lodo {e['mw']} ppg, TVD {e['tvd']:,.0f} ft).")
        resp = st.number_input("Calculá la densidad de matar, KMW (ppg)", 8.0, 25.0, 10.0, 0.01, key="esc_kmw")
        if st.button("Verificar KMW"):
            real = kmw(e["sidpp"], e["tvd"], e["mw"])
            if abs(resp - real) <= 0.1:
                st.success(f"Correcto: KMW = {real:.2f} ppg.")
            else:
                st.error("Revisá la fórmula: KMW = SIDPP / (0.052 x TVD) + densidad actual.")
    if st.button("Nuevo escenario"):
        _nuevo(tipo)
        st.rerun()


def _nuevo_gas():
    st.session_state.gas = {"sicp0": random.randrange(300, 501, 10), "rise": 0, "turno": 0,
                            "errores": 0, "fin": False,
                            "log": ["Pozo cerrado. Las presiones suben con las bombas apagadas (gas migratorio)."]}


def _ejecutar_gas(accion):
    g = st.session_state.gas
    if g["fin"]:
        return
    g["turno"] += 1
    if accion == ACC_GAS[0]:
        if g["rise"] >= 100:
            g["errores"] += 1
            g["log"].append("Error: el colchón de 50-100 psi ya se superó; había que purgar.")
        g["rise"] += random.randrange(30, 61, 10)
        g["log"].append(f"Esperás 15 min. Incremento acumulado: {g['rise']} psi.")
    elif accion == ACC_GAS[1]:
        if g["rise"] >= 50:
            g["rise"] -= 50
            g["log"].append("Purgás un volumen pequeño: el gas se expande y la presión baja 50 psi.")
        else:
            g["errores"] += 1
            g["log"].append("Error: sin colchón de presión, purgar baja la BHP bajo la presión de formación.")
    elif accion == ACC_GAS[2]:
        if g["turno"] >= 6:
            g["fin"] = True
            g["log"].append("El gas llegó a superficie y lo desviás al Pobre Boy.")
        else:
            g["errores"] += 1
            g["log"].append("Error: el influjo todavía no llegó a superficie.")
    else:
        g["errores"] += 2
        g["log"].append("Error grave: abrir el pozo por completo hace perder el control.")
    if g["turno"] >= 10 and not g["fin"]:
        g["fin"] = True
        g["errores"] += 1
        g["log"].append("Se acabó el tiempo sin desviar el flujo.")


def _escenario_gas():
    if "gas" not in st.session_state:
        _nuevo_gas()
    g = st.session_state.gas
    alarma = g["rise"] >= 100 and not g["fin"]
    st.image(_sala_control((g["rise"], 150, "Incremento SICP", "psi"), (g["sicp0"] + g["rise"], 3000, "SICP", "psi"),
                           (g["turno"], 10, "Turno", ""), True, alarma), use_container_width=True)
    m = st.columns(3)
    m[0].metric("SICP (psi)", f"{g['sicp0'] + g['rise']}", f"+{g['rise']}")
    m[1].metric("Turno", f"{g['turno']} / 10")
    m[2].metric("Errores", g["errores"])
    if alarma:
        st.error("El colchón de 50-100 psi se superó: hay que purgar.")
    if not g["fin"]:
        st.selectbox("Acción", ACC_GAS, key="gas_accion")
        st.button("Ejecutar acción", type="primary", on_click=lambda: _ejecutar_gas(st.session_state["gas_accion"]))
    st.markdown("**Bitácora**")
    for linea in reversed(g["log"][-8:]):
        st.write("• " + linea)
    if g["fin"]:
        st.success(f"Escenario terminado. Puntaje: {max(0, 100 - 20 * g['errores'])} / 100.")
    if st.button("Nuevo escenario"):
        _nuevo_gas()
        st.rerun()


def modulo_escenario():
    st.subheader("Escenarios de control de pozo")
    tipo = st.selectbox("Escenario", list(CFG) + ["Gas migratorio con pozo cerrado"], key="esc_tipo")
    if tipo.startswith("Gas"):
        _escenario_gas()
    else:
        _escenario_kick(tipo)


# ----------------------------------------------------------------------------
# MODULO 5: MANUAL MAESTRO DE PERFORACIÓN 3.0
# ----------------------------------------------------------------------------
def modulo_manual():
    st.subheader("Manual Maestro de Perforación 3.0")
    st.markdown("""
    ### Guía Rápida y Fórmulas
    
    #### 1. Hidráulica y Sarta
    - **Factor de Flotación ($FF$):**  
      $$FF = \\frac{65.5 - MW}{65.5}$$
    - **Presión Hidrostática en Fondo ($BHP$):**  
      $$BHP = 0.052 \\times MW \\times TVD$$
    - **Densidad Equivalente de Circulación ($ECD$):**  
      $$ECD = MW + \\frac{\\Delta P_{anular}}{0.052 \\times TVD}$$
    - **Punto Neutro:**  
      $$Punto\\ Neutro = \\frac{WOB}{W_{DC} \\times FF}$$
    
    ---
    
    #### 2. Control de Pozos
    - **Densidad del Lodo de Ahogo ($KMW$):**  
      $$KMW = \\frac{SIDPP}{0.052 \\times TVD} + MW$$
    - **Presión Inicial de Circulación ($ICP$):**  
      $$ICP = SIDPP + SCR$$
    - **Presión Final de Circulación ($FCP$):**  
      $$FCP = SCR \\times \\frac{KMW}{MW}$$
    - **Presión Máxima Admisible en Anular ($MAASP$):**  
      $$MAASP = 0.052 \\times (EMW_{frac} - MW) \\times TVD_{zapato}$$
    
    ---
    
    #### 3. Métodos Operativos
    - **Cierre Duro:** Ante una ganancia en piletas (*Pit Gain*), detener bombas, espaciar la sarta, cerrar el BOP anular/ariete y abrir la HCR.
    - **Método Volumétrico (Gas Migratorio):** Mantener la BHP constante permitiendo la expansión controlada del gas mediante el purgado paulatino por el *choke*.
    """)


# ----------------------------------------------------------------------------
# ENTRADA PRINCIPAL
# ----------------------------------------------------------------------------
def mostrar_simulador():
    st.title("Simulador Integral MENFA")
    st.caption("Basado en el Manual Maestro de Perforación 3.0 · Material educativo")
    t1, t2, t3, t4, t5 = st.tabs([
        "Hidráulica y sarta",
        "Control de pozos",
        "Direccional",
        "Escenarios de control",
        "Manual Maestro"
    ])
    with t1:
        modulo_hidraulica()
    with t2:
        modulo_control()
    with t3:
        modulo_direccional()
    with t4:
        modulo_escenario()
    with t5:
        modulo_manual()


if __name__ == "__main__":
    st.set_page_config(page_title="Simulador MENFA", page_icon="🛢️", layout="wide")
    mostrar_simulador()
