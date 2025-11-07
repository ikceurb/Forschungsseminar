import json
import pandas as pd
from collections import defaultdict
import heapq
from types import SimpleNamespace 

# --- 1. KLASSENDEFINITIONEN ---

class Auftrag:
    """ Repräsentiert einen einzelnen Transportauftrag. """
    def __init__(self, order_id, anzahl_waggons, laenge, gewicht, origin, destination, latest_arrival_time):
        self.order_id = order_id
        self.anzahl_waggons = anzahl_waggons
        self.laenge = laenge
        self.gewicht = gewicht
        self.origin = origin
        self.destination = destination
        self.latest_arrival_time = latest_arrival_time
    def __repr__(self):
        return (f"Auftrag(ID: {self.order_id}, Von: {self.origin}, Nach: {self.destination}, "
                f"Waggons: {self.anzahl_waggons})")

class Rangierbahnhof:
    """ Repräsentiert einen physischen Rangierbahnhof. """
    def __init__(self, yard_id, rangier_dauer, kapazitaet, kosten_pro_wagen):
        self.yard_id = yard_id
        self.rangier_dauer = rangier_dauer
        self.kapazitaet = kapazitaet
        self.kosten_pro_wagen = kosten_pro_wagen
    def __repr__(self):
        return (f"Bahnhof(ID: {self.yard_id}, Dauer: {self.rangier_dauer}, "
                f"Kapazität: {self.kapazitaet}, Kosten: {self.kosten_pro_wagen})")

class BlockingPfad:
    """ Repräsentiert eine physische Strecke (Template). """
    def __init__(self, blocking_arc_id, origin_yard_id, dest_yard_id, 
                 duration, max_length, max_weight):
        self.origin_yard_id = origin_yard_id
        self.dest_yard_id = dest_yard_id
        self.duration = duration
        self.max_length = max_length
        self.max_weight = max_weight
        self.blocking_arc_id = blocking_arc_id 
    def __repr__(self):
        return (f"Strecke(ID: {self.blocking_arc_id}, "
                f"Von: {self.origin_yard_id} -> Nach: {self.dest_yard_id}, "
                f"Dauer: {self.duration})")

# --- 2. K-SHORTEST-PATH HILFSFUNKTION ---

def _finde_top_k_pfade(start_node_id, end_node_id, k, graph, bahnhof_map):
    """
    Findet die 'k' kürzesten einfachen Pfade (ohne Zyklen).
    Kostenmetrik (C_kq): Summe(t_a + w_a) für alle Strecken 'a' im Pfad.
    """
    tie_breaker = 0
    pq = [(0, tie_breaker, [])]
    gefundene_pfade = []

    while pq and len(gefundene_pfade) < k:
        (kosten, _, pfad) = heapq.heappop(pq)
        aktueller_knoten_id = start_node_id if not pfad else pfad[-1].dest_yard_id
            
        if aktueller_knoten_id == end_node_id:
            gefundene_pfade.append((kosten, pfad))
            continue 

        besuchte_knoten = {start_node_id}
        for strecke in pfad:
            besuchte_knoten.add(strecke.dest_yard_id)

        for strecke in graph[aktueller_knoten_id]:
            naechster_knoten_id = strecke.dest_yard_id
            
            if naechster_knoten_id not in besuchte_knoten:
                # Kostenberechnung (Fahrzeit + Rangierzeit am ZIEL der Strecke)
                neue_kosten = kosten + strecke.duration + bahnhof_map[strecke.dest_yard_id].rangier_dauer
                neuer_pfad = pfad + [strecke]
                tie_breaker += 1
                heapq.heappush(pq, (neue_kosten, tie_breaker, neuer_pfad))
                
    return [pfad for kosten, pfad in gefundene_pfade]

# --- 3. HAUPTFUNKTION ZUR DATENVERARBEITUNG ---

def lade_daten(json_dateipfad, anzahl_pfade=3):
    """
    Lädt die JSON-Datei, verarbeitet sie und gibt alle notwendigen
    Parameter und Objektlisten für das Optimierungsmodell zurück.
    
    :param json_dateipfad: Pfad zur JSON-Datei.
    :param anzahl_pfade: Die Anzahl der (kürzesten) Pfade, die pro Auftrag 
                         generiert werden sollen (Standard: 3).
    :return: Ein Dictionary, das alle Listen und Parameter-Dictionaries enthält.
    """
    
    print(f"--- Starte Datenverarbeitung aus '{json_dateipfad}' ---")
    
    # --- A. Initialisierung der Speicherobjekte ---
    auftrags_liste = []
    bahnhof_liste = []
    strecken_liste = []
    bahnhof_map = {}
    
    # Rückgabe-Dictionaries
    Qk = {}
    Pfad_Definitionen = {}
    delta_kqa = {}
    C_kq = {}
    xi_ia = {}
    t_a = {}
    w_a = {}
    chi_a = {}
    u_a = {}
    V_i = {}
    N_i = {}
    d_k = {}
    T_k = {}
    S = [] # Bahnhof-IDs
    A = [] # Strecken-IDs
    K = [] # Auftrags-IDs

    try:
        # --- B. DATENEXTRAKTION (Aufträge, Bahnhöfe, Strecken) ---
        print("Schritt 1: Lade und extrahiere JSON-Rohdaten...")
        
        with open(json_dateipfad, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Aufträge
        for order_json in data['Orders']:
            auftrags_liste.append(Auftrag(
                order_id=order_json['OrderId']['Value'],
                anzahl_waggons=order_json['NumberOfFreightCars']['Value'],
                laenge=order_json['OrderLength']['Value'],
                gewicht=order_json['OrderWeight']['Value'],
                origin=order_json['Origin']['ShuntingYard']['YardId']['Value'],
                destination=order_json['Destination']['ShuntingYard']['YardId']['Value'],
                latest_arrival_time=order_json['MaxTimeUntilArrival']['Value']
            ))

        # Bahnhöfe
        einzigartige_bahnhofe = {} 
        for node in data['Network']['Nodes']['YardNodes']:
            yard_data = node['ShuntingYard']
            yard_id = yard_data['YardId']['Value']
            if yard_id not in einzigartige_bahnhofe:
                neuer_bahnhof = Rangierbahnhof(
                    yard_id=yard_id,
                    rangier_dauer=yard_data['ShuntingDuration']['Value'],
                    kapazitaet=yard_data['FreightCarCapacity']['Value'],
                    kosten_pro_wagen=yard_data['ShuntingCostPerCar']['Cost']['Value']
                )
                einzigartige_bahnhofe[yard_id] = neuer_bahnhof
        bahnhof_liste = list(einzigartige_bahnhofe.values())
        bahnhof_liste.sort(key=lambda bhf: int(bhf.yard_id.replace("ShuntingYard", "")))
        bahnhof_map = {bhf.yard_id: bhf for bhf in bahnhof_liste}

        # Strecken (BlockingPfade)
        i = 0
        gesehene_verbindungen = set()
        for arc_json in data['Network']['Arcs']['DrivingArcs']:
            origin_id = arc_json['YardFrom']['ShuntingYard']['YardId']['Value']
            dest_id = arc_json['YardTo']['ShuntingYard']['YardId']['Value']
            verbindung_tupel = (origin_id, dest_id)
            if verbindung_tupel not in gesehene_verbindungen:
                arc_id = "B"+str(i)
                neue_strecke = BlockingPfad(
                    origin_yard_id=origin_id,
                    dest_yard_id=dest_id,
                    duration=arc_json['Duration']['Value'],
                    max_length=arc_json['MaximalTrainLength']['Value'],
                    max_weight=arc_json['MaximalTrainWeight']['Value'],
                    blocking_arc_id=arc_id,
                )
                i += 1
                strecken_liste.append(neue_strecke)
                gesehene_verbindungen.add(verbindung_tupel)
        
        print(f"Datenextraktion abgeschlossen: {len(auftrags_liste)} Aufträge, "
              f"{len(bahnhof_liste)} Bahnhöfe, {len(strecken_liste)} Strecken.")

        # --- C. GRAPH-ERSTELLUNG & PFADSUCHE (Qk, C_kq, delta_kqa) ---
        print(f"\nSchritt 2: Erstelle Graph und suche Top {anzahl_pfade} Pfade pro Auftrag...")
        
        graph = defaultdict(list)
        for strecke in strecken_liste:
            graph[strecke.origin_yard_id].append(strecke)
            
        # Temporäre Maps für Kostenberechnung
        _t_a = {s.blocking_arc_id: s.duration for s in strecken_liste}
        _w_a_ziel = {s.blocking_arc_id: bahnhof_map[s.dest_yard_id].rangier_dauer 
                   for s in strecken_liste}

        pfad_zaehler = 1
        for k in auftrags_liste:
            k_id = k.order_id
            
            gefundene_pfade_obj = _finde_top_k_pfade(k.origin, k.destination, anzahl_pfade, graph, bahnhof_map)
            
            kandidaten_pfad_ids = []
            if not gefundene_pfade_obj:
                print(f"WARNUNG: Für Auftrag {k_id} (Von {k.origin} nach {k.destination}) wurde kein Pfad gefunden.")
            
            for pfad_obj_liste in gefundene_pfade_obj:
                q_id = f"P{pfad_zaehler}"
                pfad_zaehler += 1
                
                kandidaten_pfad_ids.append(q_id)
                Pfad_Definitionen[q_id] = pfad_obj_liste
                
                current_kq_cost = 0
                strecken_ids_in_pfad_q = set()
                
                for strecke in pfad_obj_liste:
                    a_id = strecke.blocking_arc_id
                    strecken_ids_in_pfad_q.add(a_id)
                    current_kq_cost += _t_a[a_id] + _w_a_ziel[a_id] # Kosten = t_a + w_a(ziel)

                C_kq[(k_id, q_id)] = current_kq_cost
                
                for a in strecken_liste:
                    a_id = a.blocking_arc_id
                    delta_kqa[(k_id, q_id, a_id)] = 1 if a_id in strecken_ids_in_pfad_q else 0
                        
            Qk[k_id] = kandidaten_pfad_ids
        
        print(f"Pfadsuche abgeschlossen. {len(Pfad_Definitionen)} einzigartige Pfade gefunden.")

        # --- D. PARAMETER-DICTIONARIES ERSTELLEN ---
        print("\nSchritt 3: Erstelle finale Parameter-Dictionaries...")
        
        # Sets S, A, K
        S = [bhf.yard_id for bhf in bahnhof_liste]
        A = [s.blocking_arc_id for s in strecken_liste]
        K = [a.order_id for a in auftrags_liste]

        # xi_ia Matrix (Bahnhof-Start-Strecke)
        for bahnhof in bahnhof_liste:
            i_id = bahnhof.yard_id
            for strecke in strecken_liste:
                a_id = strecke.blocking_arc_id
                xi_ia[(i_id, a_id)] = 1 if bahnhof.yard_id == strecke.origin_yard_id else 0

        # Block-Parameter (a)
        for strecke in strecken_liste:
            a_id = strecke.blocking_arc_id
            t_a[a_id] = strecke.duration 
            w_a[a_id] = bahnhof_map[strecke.origin_yard_id].rangier_dauer # w_a = Rangierzeit am START
            chi_a[a_id] = 1000 # Placeholder
            u_a[a_id] = 100 # Placeholder

        # Stations-Parameter (i)
        for bahnhof in bahnhof_liste:
            i_id = bahnhof.yard_id
            V_i[i_id] = bahnhof.kapazitaet
            N_i[i_id] = 20 # Placeholder

        # Sendungs-Parameter (k)
        for auftrag in auftrags_liste:
            k_id = auftrag.order_id
            d_k[k_id] = auftrag.anzahl_waggons
            T_k[k_id] = auftrag.latest_arrival_time

        print("Parameter-Erstellung abgeschlossen.")

# --- E. RÜCKGABE ---
        
        print(f"\n--- Datenverarbeitung erfolgreich abgeschlossen ---")
        
        # Alle erstellten Objekte in einem SimpleNamespace-Objekt zurückgeben
        return SimpleNamespace(
            # --- Mengen (Listen von IDs) ---
            S = S, # Bahnhöfe
            A = A, # Strecken (Blöcke)
            K = K, # Aufträge (Sendungen)
            
            # --- Objektlisten (falls benötigt) ---
            obj_auftraege = auftrags_liste,
            obj_bahnhofe = bahnhof_liste,
            obj_strecken = strecken_liste,
            obj_pfade = Pfad_Definitionen,
            
            # --- Parameter für Aufträge (k) ---
            Qk = Qk,       # Dict: k -> [q1, q2, ...]
            d_k = d_k,     # Dict: k -> anzahl_waggons
            T_k = T_k,     # Dict: k -> max_zeit
            
            # --- Parameter für Pfade (k, q) ---
            C_kq = C_kq,   # Dict: (k, q) -> gesamtkosten (t_a + w_a(ziel))
            
            # --- Parameter für Strecken (a) ---
            t_a = t_a,     # Dict: a -> fahrzeit
            w_a = w_a,     # Dict: a -> rangierzeit (am START)
            chi_a = chi_a, # Dict: a -> platzhalter-kosten (1000)
            u_a = u_a,     # Dict: a -> platzhalter-kapazität (100)
            
            # --- Parameter für Bahnhöfe (i) ---
            V_i = V_i,     # Dict: i -> kapazität
            N_i = N_i,     # Dict: i -> platzhalter-max-züge (20)
            
            # --- Matrizen (als Dictionaries) ---
            delta_kqa = delta_kqa, # Dict: (k, q, a) -> 0 oder 1
            xi_ia = xi_ia          # Dict: (i, a) -> 0 oder 1
        )

    except FileNotFoundError:
        print(f"FEHLER: Die Datei '{json_dateipfad}' wurde nicht gefunden.")
        return None
    except KeyError as e:
        print(f"FEHLER: Unerwartete JSON-Struktur. Fehlender Schlüssel: {e}")
        return None
    except Exception as e:
        print(f"Ein unerwarteter Fehler ist aufgetreten: {e}")
        return None