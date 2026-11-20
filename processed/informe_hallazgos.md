# Hallazgos: ¿Defense wins championships?

Generado por `data/scripts/modelado.py`. Datos: 122 partidos, 32 equipos, semanas 1 a 8 de 2021.

## Limitaciones que condicionan toda conclusión

- `plays.csv` contiene solo dropbacks (pases, sacks, scrambles). No hay jugadas de carrera: **todo es defensa contra el pase**.
- No hay marcador final en los datos del concurso. Se **estima** con el marcador previo a la última jugada observada
  (+6 si fue touchdown). Puede omitir carreras o goles de campo posteriores. 69 partidos tienen diferencia <= 10
  y su ganador puede estar mal; usa `resultado_incierto` en `games_clean.csv` para filtrarlos.
- Cada equipo tiene unos 7 a 8 partidos: el win% es ruidoso. Los intervalos de confianza son anchos.

## 1. Métrica nueva: DCI (Defensive Control Index)

DCI = P(éxito ofensivo | situación) - P(éxito ofensivo | situación + estado de tracking al soltar el balón), en puntos
porcentuales por dropback. Positivo: la defensa dejó a la ofensiva en peor posición de lo que down, distancia, yarda,
marcador y play action predecían. Se calcula con regresión logística y validación cruzada agrupada por partido, así
que no se evalúa sobre jugadas con las que se entrenó.

Entradas de tracking, medidas a reloj fijo (2.0 s tras el snap, o la liberación si fue antes): presión (rusher a
<= 2 yd del QB), distancia del rusher más cercano, rushers a <= 5 yd, velocidad de los rushers, separación media y
mínima entre receptores y defensor más cercano, % de rutas abiertas (>= 3 yd), cuánto se cerró la cobertura desde el
snap y número de rushers. No usa el tiempo hasta soltar ni el estado al soltar: dependen de cuándo decide lanzar la
ofensiva y de si hubo sack. Un pase rápido (liberación antes de 2.0 s) entra como control de situación.

Métrica complementaria PRS (Pressure Rate per Second) = jugadas con presión / segundos totales de dropback del equipo.
Corrige que las defensas contra pases rápidos tienen menos tiempo para llegar al QB.

| Modelo | AUC | Logloss |
|---|---|---|
| Solo situación | 0.625 | 0.665 |
| Situación + tracking | 0.627 | 0.665 |
| Solo tracking | 0.548 | |

(8,556 jugadas con tracking completo). Si "Situación + tracking" casi no mejora a "Solo situación", la
estructura defensiva a reloj fijo describe cómo juega el equipo más que el resultado de cada jugada.

Coeficientes estandarizados (ver `dci_coeficientes.csv`):

| variable | grupo | coef_estandarizado |
|---|---|---|
| down2 | situacion | -0.162 |
| down3 | situacion | -0.231 |
| down4 | situacion | -0.131 |
| yardsToGo | situacion | -0.379 |
| ytg_x_d3 | situacion | -0.204 |
| yardline_100 | situacion | 0.062 |
| zona_roja | situacion | -0.069 |
| play_action | situacion | -0.020 |
| def_margen | situacion | 0.007 |
| llego_2s | situacion | -0.111 |
| presion_t2 | tracking | 0.014 |
| rush_dist_t2 | tracking | 0.125 |
| rush_n5_t2 | tracking | 0.084 |
| rush_vel_t2 | tracking | -0.073 |
| sep_media_t2 | tracking | -0.015 |
| sep_min_t2 | tracking | 0.001 |
| pct_abiertas_t2 | tracking | 0.027 |
| cierre_cobertura_t2 | tracking | -0.033 |
| n_rushers | tracking | -0.024 |

## 2. Defensa y victorias por equipo

Correlación con win% (n = 32 equipos). Para todas las métricas, más alto = mejor.

| metrica | lado | n_equipos | pearson (IC95) | spearman |
|---|---|---|---|---|
| def_exito_def | defensa | 32 | 0.43 [0.13, 0.67] | 0.42 |
| def_yds_dropback | defensa | 32 | 0.56 [0.29, 0.74] | 0.49 |
| def_sack_rate | defensa | 32 | -0.02 [-0.33, 0.31] | -0.01 |
| def_int_rate | defensa | 32 | 0.54 [0.26, 0.75] | 0.53 |
| def_presion_pff | defensa | 32 | 0.14 [-0.20, 0.46] | 0.14 |
| def_prs | defensa | 32 | 0.21 [-0.09, 0.53] | 0.34 |
| def_dci | defensa | 32 | 0.13 [-0.20, 0.44] | 0.16 |
| of_exito | ofensiva | 32 | 0.54 [0.25, 0.74] | 0.52 |
| of_yds_dropback | ofensiva | 32 | 0.64 [0.44, 0.79] | 0.63 |
| of_proteccion | ofensiva | 32 | 0.09 [-0.28, 0.42] | 0.09 |
| of_oci | ofensiva | 32 | 0.36 [0.09, 0.61] | 0.41 |

Correlación con margen de puntos por partido:

| metrica | pearson (IC95) | spearman |
|---|---|---|
| def_exito_def | 0.48 [0.17, 0.72] | 0.44 |
| def_yds_dropback | 0.70 [0.46, 0.84] | 0.59 |
| def_sack_rate | 0.07 [-0.21, 0.34] | 0.10 |
| def_int_rate | 0.58 [0.28, 0.80] | 0.59 |
| def_presion_pff | 0.27 [-0.07, 0.57] | 0.21 |
| def_prs | 0.25 [-0.01, 0.51] | 0.29 |
| def_dci | 0.06 [-0.33, 0.39] | 0.06 |
| of_exito | 0.48 [0.21, 0.69] | 0.51 |
| of_yds_dropback | 0.70 [0.53, 0.83] | 0.71 |
| of_proteccion | 0.16 [-0.24, 0.47] | 0.06 |
| of_oci | 0.23 [-0.09, 0.52] | 0.12 |

Win% promedio por cuartil de equipos ordenados por métrica:

| cuartil | win% por defensa (exito) | win% por defensa (DCI) | win% por ofensiva (exito) |
|---|---|---|---|
| Q1 (peor) | 0.305 | 0.463 | 0.421 |
| Q2 | 0.564 | 0.463 | 0.419 |
| Q3 | 0.530 | 0.512 | 0.451 |
| Q4 (mejor) | 0.607 | 0.567 | 0.715 |

Regresión a nivel equipo (betas estandarizados con ambos lados a la vez; si el beta de defensa no supera al de
ofensiva, los datos no respaldan que la defensa pese más):

| familia | objetivo | lado | n_equipos | beta (IC95) | r2 |
|---|---|---|---|---|---|
| Yardas/dropback | win_pct | defensa | 32 | 0.37 [0.14, 0.64] | 0.52 |
| Yardas/dropback | win_pct | ofensiva | 32 | 0.50 [0.29, 0.70] | 0.52 |
| Yardas/dropback | margen_pp | defensa | 32 | 0.51 [0.32, 0.71] | 0.71 |
| Yardas/dropback | margen_pp | ofensiva | 32 | 0.50 [0.34, 0.69] | 0.71 |
| Éxito por jugada | win_pct | defensa | 32 | 0.36 [0.07, 0.66] | 0.41 |
| Éxito por jugada | win_pct | ofensiva | 32 | 0.48 [0.18, 0.76] | 0.41 |
| Éxito por jugada | margen_pp | defensa | 32 | 0.41 [0.11, 0.75] | 0.40 |
| Éxito por jugada | margen_pp | ofensiva | 32 | 0.42 [0.12, 0.72] | 0.40 |
| DCI / OCI | win_pct | defensa | 32 | 0.11 [-0.17, 0.44] | 0.14 |
| DCI / OCI | win_pct | ofensiva | 32 | 0.35 [0.06, 0.67] | 0.14 |
| DCI / OCI | margen_pp | defensa | 32 | 0.04 [-0.30, 0.39] | 0.05 |
| DCI / OCI | margen_pp | ofensiva | 32 | 0.22 [-0.12, 0.55] | 0.05 |

## 3. Defensa contra ofensiva para predecir partidos

Cada partido se predice con la calidad de cada equipo calculada sin ese partido. Coeficientes estandarizados
(por desviación estándar de la diferencia local - visita).

| familia | modelo | variable | coef (IC95) | coef_margen_pts_por_sd | precision_cv | r2_margen_cv |
|---|---|---|---|---|---|---|
| Éxito (defensa vs ofensiva) | solo defensa | defensa | 0.26 [-0.13, 0.66] | 3.39 | 0.54 | 0.02 |
| Éxito (defensa vs ofensiva) | solo ofensiva | ofensiva | 0.30 [-0.06, 0.74] | 2.50 | 0.54 | -0.00 |
| Éxito (defensa vs ofensiva) | defensa + ofensiva | defensa | 0.26 [-0.10, 0.66] | 3.33 | 0.51 | 0.02 |
| Éxito (defensa vs ofensiva) | defensa + ofensiva | ofensiva | 0.29 [-0.12, 0.73] | 2.41 | 0.51 | 0.02 |
| Yardas/dropback | solo defensa | defensa | 0.35 [0.01, 0.70] | 4.99 | 0.48 | 0.07 |
| Yardas/dropback | solo ofensiva | ofensiva | 0.49 [0.09, 0.94] | 5.15 | 0.55 | 0.08 |
| Yardas/dropback | defensa + ofensiva | defensa | 0.23 [-0.17, 0.62] | 3.67 | 0.57 | 0.08 |
| Yardas/dropback | defensa + ofensiva | ofensiva | 0.42 [0.02, 0.92] | 3.93 | 0.57 | 0.08 |
| DCI (defensa) vs OCI (ofensiva) | solo defensa | defensa | 0.14 [-0.22, 0.53] | 0.69 | 0.43 | -0.04 |
| DCI (defensa) vs OCI (ofensiva) | solo ofensiva | ofensiva | 0.47 [0.11, 0.90] | 2.76 | 0.54 | -0.00 |
| DCI (defensa) vs OCI (ofensiva) | defensa + ofensiva | defensa | 0.14 [-0.24, 0.55] | 0.63 | 0.59 | -0.01 |
| DCI (defensa) vs OCI (ofensiva) | defensa + ofensiva | ofensiva | 0.47 [0.12, 0.88] | 2.75 | 0.59 | -0.01 |

## 4. Estabilidad de las métricas

Correlación entre mitades de partidos de cada equipo (pares vs impares). Una métrica estable describe al equipo, no
al azar de unos partidos.

| metrica | confiabilidad_split_half | spearman_brown | predice_win_pct_otra_mitad |
|---|---|---|---|
| def_exito_def | 0.18 | 0.30 | 0.06 |
| def_yds_dropback | 0.19 | 0.31 | 0.11 |
| def_int_rate | 0.38 | 0.56 | 0.28 |
| def_sack_rate | -0.21 | -0.52 | 0.07 |
| def_presion_pff | -0.04 | -0.08 | 0.11 |
| def_prs | 0.29 | 0.44 | 0.01 |
| def_dci | 0.71 | 0.83 | 0.13 |
| of_exito | 0.32 | 0.49 | 0.34 |
| of_oci | 0.46 | 0.63 | 0.35 |

## 5. Patrones defensivos

Cobertura (ordenadas por éxito defensivo):

| cobertura | jugadas | exito_def | yds_permitidas | sack_rate | int_rate | explosivas | presion_pff | sep_media | dci |
|---|---|---|---|---|---|---|---|---|---|
| Red Zone | 376 | 0.564 | 2.298 | 0.072 | 0.027 | 0.000 | 0.428 | 2.488 | -0.398 |
| Cover-1 | 2011 | 0.538 | 6.655 | 0.077 | 0.017 | 0.117 | 0.404 | 2.169 | 0.443 |
| 2-Man | 200 | 0.535 | 7.930 | 0.095 | 0.020 | 0.135 | 0.405 | 2.104 | 0.169 |
| Quarters | 1033 | 0.520 | 7.041 | 0.053 | 0.023 | 0.094 | 0.356 | 3.584 | -0.337 |
| Cover-2 | 1085 | 0.516 | 6.509 | 0.060 | 0.025 | 0.104 | 0.341 | 4.263 | -0.395 |
| Cover-0 | 270 | 0.511 | 5.037 | 0.044 | 0.019 | 0.089 | 0.511 | 2.609 | 1.593 |
| Cover-6 | 805 | 0.494 | 6.875 | 0.052 | 0.030 | 0.091 | 0.340 | 3.679 | -0.156 |
| Cover-3 | 2665 | 0.486 | 6.904 | 0.060 | 0.020 | 0.097 | 0.363 | 3.692 | -0.094 |

Rushers:

| rushers_cat | jugadas | exito_def | yds_permitidas | sack_rate | int_rate | explosivas | presion_pff | sep_media | dci |
|---|---|---|---|---|---|---|---|---|---|
| <=3 | 438 | 0.541 | 7.361 | 0.039 | 0.030 | 0.096 | 0.237 | 3.315 | -1.212 |
| 4 | 6011 | 0.510 | 6.532 | 0.058 | 0.022 | 0.094 | 0.351 | 3.370 | -0.389 |
| 5 | 1689 | 0.509 | 6.492 | 0.090 | 0.020 | 0.112 | 0.467 | 3.001 | 1.243 |
| 6+ | 418 | 0.543 | 6.483 | 0.067 | 0.024 | 0.110 | 0.517 | 2.569 | 1.918 |

Presión por separación (cobertura pegada, media, suelta):

| presion | sep_tercil | jugadas | exito_def | yds_permitidas | sack_rate | int_rate | explosivas | presion_pff | sep_media | dci |
|---|---|---|---|---|---|---|---|---|---|---|
| con presion | cobertura pegada | 1201 | 0.675 | 3.557 | 0.194 | 0.014 | 0.080 | 1.000 | 1.835 | 1.055 |
| con presion | media | 954 | 0.627 | 4.394 | 0.143 | 0.027 | 0.069 | 1.000 | 3.128 | 0.920 |
| con presion | cobertura suelta | 1061 | 0.660 | 3.950 | 0.164 | 0.030 | 0.086 | 1.000 | 4.860 | 0.455 |
| sin presion | cobertura pegada | 1651 | 0.460 | 7.571 | 0.000 | 0.022 | 0.116 | 0.000 | 1.889 | -0.001 |
| sin presion | media | 1898 | 0.419 | 8.013 | 0.000 | 0.019 | 0.102 | 0.000 | 3.121 | -0.503 |
| sin presion | cobertura suelta | 1791 | 0.404 | 8.820 | 0.000 | 0.023 | 0.114 | 0.000 | 4.727 | -0.914 |

Tiempo hasta soltar:

| t_lanzar | jugadas | exito_def | yds_permitidas | sack_rate | int_rate | explosivas | presion_pff | sep_media | dci |
|---|---|---|---|---|---|---|---|---|---|
| <2.3s | 2282 | 0.431 | 6.367 | 0.003 | 0.011 | 0.051 | 0.159 | 3.202 | 0.411 |
| 2.3-2.8s | 2065 | 0.478 | 7.376 | 0.016 | 0.021 | 0.104 | 0.301 | 3.043 | 0.262 |
| 2.8-3.3s | 1550 | 0.504 | 7.739 | 0.035 | 0.035 | 0.131 | 0.368 | 3.317 | -0.322 |
| >3.3s | 2659 | 0.615 | 5.417 | 0.168 | 0.025 | 0.116 | 0.625 | 3.430 | -0.356 |
