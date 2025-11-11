Optimierungsmodell für das Railroad Blocking Problem (RBP)

Dieses Repository enthält eine Gurobi-Python-Implementierung eines Optimierungsmodells für das Railroad Blocking Problem (RBP), basierend auf der Formulierung von Hasany & Shafahi (2018).
Das Modell löst ein taktisches Planungsproblem im Schienengüterverkehr (SGV), speziell im Einzelwagenverkehr. Es optimiert den zentralen Trade-off zwischen:
- Transportkosten: (Monetärer Wert der Reise- und Wartezeit der Wagen)
- Betriebskosten: (Fixkosten für den Einsatz von Zügen auf Streckenabschnitten/Blöcken)

Ziel ist es, unter Einhaltung von Nachfrage, Kapazitätsgrenzen und maximalen Reisezeiten einen minimalen Gesamtkostenplan zu finden.

Anforderungen:

Python 3.x

gurobipy Python-Paket

Wissenschaftlicher Kontext 

Paper: Hasany, R. M., & Shafahi, Y. (2018). Modeling formulation and a new heuristic for the railroad blocking problem. Applied Mathematical Modelling, 56, 304-324.

Datensätze: https://www.researchgate.net/publication/351746800_Data-SCRMTSP-Instances-2021
