import json
import pandas as pd
from collections import defaultdict
import heapq
from types import SimpleNamespace 

# 1. KLASSENDEFINITIONEN

class Auftrag:
    def __init__(self, order_id, anzahl_waggons, laenge, gewicht, origin, destination, latest_arrival_time):
        self.order_id = order_id
        self.anzahl_waggons = anzahl_waggons
        self.laenge = laenge
        self.gewicht = gewicht
        self.origin = origin
        self.destination = destination
        self.latest_arrival_time = latest_arrival_time
    def __repr__(self):
        return (f"Auftrag({self.order_id}, {self.origin}->{self.destination}, {self.anzahl_waggons} Wag.)")

class Rangierbahnhof:
    def __init__(self, yard_id, rangier_dauer, kapazitaet, kosten_pro_wagen,dispatch_kapazität):
        self.yard_id = yard_id
        self.rangier_dauer = rangier_dauer
        self.kapazitaet = kapazitaet
        self.kosten_pro_wagen = kosten_pro_wagen
        self.dispatch_kapazität = dispatch_kapazität
    def __repr__(self):
        return f"Bahnhof({self.yard_id}, Dauer:{self.rangier_dauer})"

class PhysischeStrecke:
    """ Repräsentiert ein physisches Gleis zwischen zwei direkten Nachbarn (aus DrivingArcs). """
    def __init__(self, origin_id, dest_id, duration, max_length, max_weight):
        self.origin_id = origin_id
        self.dest_id = dest_id
        self.duration = duration
        self.max_length = max_length
        self.max_weight = max_weight
    def __repr__(self):
        return f"Physisch({self.origin_id}->{self.dest_id}, t={self.duration})"

class LogischerBlock:
    """ 
    Repräsentiert einen potenziellen Block 'a' für das mathematische Modell.
    Ein Block ist eine Sequenz von physischen Strecken ohne Zwischenklassifizierung (Bypass).
    """
    def __init__(self, block_id, origin_yard_id, dest_yard_id, 
                 total_duration, min_max_length, min_max_weight, physical_hops):
        self.block_id = block_id
        self.origin_yard_id = origin_yard_id
        self.dest_yard_id = dest_yard_id
        self.duration = total_duration      # t_a (Summe der Fahrzeiten im Block)
        self.max_length = min_max_length    # Die restriktivste Länge auf dem Weg
        self.max_weight = min_max_weight    # Das restriktivste Gewicht auf dem Weg
        self.physical_hops = physical_hops  # Liste der durchfahrenen Knoten (zur Info)
        
    def __repr__(self):
        # Zeigt z.B. "Block(Blk_5: Yard0->Yard3, t=15, via=[Yard0, Yard1, Yard2, Yard3])"
        return (f"Block({self.block_id}: {self.origin_yard_id}->{self.dest_yard_id}, "
                f"t={self.duration}, Hops={len(self.physical_hops)-1})")

# 2. Algorithmen (Block-Generierung & Pfadsuche)

def _generiere_kandidaten_bloecke(bahnhof_ids, physischer_graph, max_hops=3):
    """
    Erzeugt die Menge A (Kandidaten-Blöcke) basierend auf dem physischen Netz.
    Nutzt Tiefensuche (DFS) mit Limitierung der Kantenanzahl (Hops).
    """
    kandidaten_bloecke = []
    block_counter = 0
    
    print(f"   -> Generiere logische Blöcke (Max Hops: {max_hops})...")

    # Für jeden Bahnhof als möglichen Startpunkt eines Blocks
    for start_node in bahnhof_ids:
        
        # DFS Stack speichert: 
        # (aktueller_knoten, akkumulierte_dauer, min_laenge, min_gewicht, pfad_historie)
        stack = [(start_node, 0, float('inf'), float('inf'), [start_node])]
        
        while stack:
            curr_node, curr_dur, curr_len, curr_weight, history = stack.pop()
            
            # Ein Block ist valid, wenn wir mind. eine Kante zurückgelegt haben
            if curr_node != start_node:
                block_id = f"Blk_{block_counter}"
                block_counter += 1
                
                neuer_block = LogischerBlock(
                    block_id=block_id,
                    origin_yard_id=start_node,
                    dest_yard_id=curr_node,
                    total_duration=curr_dur,
                    min_max_length=curr_len,
                    min_max_weight=curr_weight,
                    physical_hops=history
                )
                kandidaten_bloecke.append(neuer_block)

            # Abbruchbedingung: Wenn wir das Hop-Limit erreicht haben, nicht tiefer suchen
            # history hat Länge (Hops + 1), da Startknoten enthalten ist.
            if len(history) - 1 >= max_hops:
                continue

            # Nachbarn im physischen Graphen erkunden
            if curr_node in physischer_graph:
                for edge in physischer_graph[curr_node]:
                    next_node = edge.dest_id
                    
                    # Zyklen vermeiden: Ein Block darf nicht im Kreis fahren
                    if next_node not in history:
                        new_dur = curr_dur + edge.duration
                        # Kapazität ist das Minimum aller Teilsegment-Kapazitäten
                        new_len = min(curr_len, edge.max_length)
                        new_weight = min(curr_weight, edge.max_weight)
                        new_history = history + [next_node]
                        
                        stack.append((next_node, new_dur, new_len, new_weight, new_history))
                        
    print(f"   -> {len(kandidaten_bloecke)} potenzielle Blöcke generiert.")
    return kandidaten_bloecke

def _finde_top_k_blocking_pfade(start_node_id, end_node_id, k, block_graph, bahnhof_map):
    """
    Findet k-kürzeste Pfade im BLOCK-Netzwerk (Q^k).
    Kosten C_kq = Summe über alle Blöcke a im Pfad: (t_a + w_a)
    wobei w_a die Rangierzeit am Startbahnhof des jeweiligen Blocks ist.
    """
    tie_breaker = 0
    # Heap speichert: (Gesamtkosten, tie_breaker, [Liste von Block-Objekten])
    pq = [(0, tie_breaker, [])]
    gefundene_pfade = []

    while pq and len(gefundene_pfade) < k:
        (kosten, _, pfad_bloecke) = heapq.heappop(pq)
        
        # Aktueller Ort ist das Ende des letzten Blocks (oder start_node beim Start)
        aktueller_knoten = start_node_id if not pfad_bloecke else pfad_bloecke[-1].dest_yard_id
            
        if aktueller_knoten == end_node_id:
            gefundene_pfade.append(pfad_bloecke)
            continue 

        besuchte_knoten = {start_node_id}
        for b in pfad_bloecke:
            besuchte_knoten.add(b.dest_yard_id)

        # Wir suchen nun den nächsten logischen Block, der hier startet
        if aktueller_knoten in block_graph:
            for block in block_graph[aktueller_knoten]:
                naechster_knoten = block.dest_yard_id
                
                if naechster_knoten not in besuchte_knoten:
                    # KOSTENBERECHNUNG LAUT PAPER:
                    # Jeder genutzte Block 'a' kostet: TravelTime(a) + ClassificationTime(StartNode(a))
                    
                    rangier_zeit_am_start = bahnhof_map[aktueller_knoten].rangier_dauer
                    step_cost = block.duration + rangier_zeit_am_start
                    
                    neue_kosten = kosten + step_cost
                    neuer_pfad = pfad_bloecke + [block]
                    
                    tie_breaker += 1
                    heapq.heappush(pq, (neue_kosten, tie_breaker, neuer_pfad))
                
    return gefundene_pfade

# 3. Hauptfunktion zum Laden und Verarbeiten der Daten

def lade_daten(json_dateipfad, anzahl_pfade=3, max_block_hops=3):
    """
    Lädt JSON, generiert logische Blöcke (bis max_block_hops) und berechnet Parameter.
    
    :param max_block_hops: Maximale Anzahl physischer Segmente in einem Block (Standard: 3).
    """
    print(f"Starte Datenverarbeitung aus '{json_dateipfad}'")
    
    # Initialisierung
    auftrags_liste = []
    bahnhof_liste = []
    
    # Rückgabe-Container
    Qk = {}
    Pfad_Definitionen = {} # Mapping PfadID -> Liste von Blöcken
    
    d_k = {}
    T_k = {}
    V_i = {}
    N_i = {}
    
    C_kq = {}
    delta_kqa = {}
    
    t_a = {}
    w_a = {}
    chi_a = {}
    u_a = {}
    xi_ia = {}

    try:
        # 1. JSON Laden
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

        # Bahnhöfe (Filtern der Unique IDs aus den Zeit-Knoten)
        unique_yards = {}
        for node in data['Network']['Nodes']['YardNodes']:
            yd = node['ShuntingYard']
            y_id = yd['YardId']['Value']
            if y_id not in unique_yards:
                unique_yards[y_id] = Rangierbahnhof(
                    yard_id=y_id,
                    rangier_dauer=yd['ShuntingDuration']['Value'],
                    kapazitaet=yd['FreightCarCapacity']['Value'],
                    kosten_pro_wagen=yd['ShuntingCostPerCar']['Cost']['Value'],
                    dispatch_kapazität=yd['TrainDispatchCapacity']['Value']
                )
        bahnhof_liste = list(unique_yards.values())
        
        # Sortieren für konsistente Ergebnisse 
        try:
            bahnhof_liste.sort(key=lambda x: int(''.join(filter(str.isdigit, x.yard_id))))
        except:
            bahnhof_liste.sort(key=lambda x: x.yard_id)
            
        bahnhof_map = {b.yard_id: b for b in bahnhof_liste}
        bahnhof_ids = list(bahnhof_map.keys())

        # Physische Strecken (DrivingArcs) in Adjazenzliste laden
        phys_graph_adj = defaultdict(list)
        seen_arcs = set()
        
        for arc in data['Network']['Arcs']['DrivingArcs']:
            o_id = arc['YardFrom']['ShuntingYard']['YardId']['Value']
            d_id = arc['YardTo']['ShuntingYard']['YardId']['Value']
            
            # Duplikate vermeiden 
            if (o_id, d_id) in seen_arcs: continue
            seen_arcs.add((o_id, d_id))
            
            strecke = PhysischeStrecke(
                origin_id=o_id,
                dest_id=d_id,
                duration=arc['Duration']['Value'],
                max_length=arc['MaximalTrainLength']['Value'],
                max_weight=arc['MaximalTrainWeight']['Value']
            )
            phys_graph_adj[o_id].append(strecke)

        print(f"Basisdaten: {len(auftrags_liste)} Aufträge, {len(bahnhof_liste)} Bahnhöfe, {len(seen_arcs)} physische Verbindungen.")

        # 2. Kandidaten-Blöcke generieren
        # Generiert Blöcke, die bis zu 'max_block_hops' Kanten lang sind.
        block_objekte = _generiere_kandidaten_bloecke(bahnhof_ids, phys_graph_adj, max_hops=max_block_hops)
        
        # Block-Graph bauen (für die Pfadsuche)
        block_graph_adj = defaultdict(list)
        for blk in block_objekte:
            block_graph_adj[blk.origin_yard_id].append(blk)
            
            # Parameter für Block 'a' füllen
            a_id = blk.block_id
            t_a[a_id] = blk.duration
            # w_a ist die Rangierzeit am START-Bahnhof dieses Blocks
            w_a[a_id] = bahnhof_map[blk.origin_yard_id].rangier_dauer
            
            # Kosten Zugebtrieben (chi_a): Pauschal 1000 $ pro Block
            chi_a[a_id] = 1000  
            
            # Kapazität: Standardwert 50 Wagen (oder abgeleitet aus Gewicht)
            u_a[a_id] = 25 
            
            # xi_ia: Ist Bahnhof i der Startbahnhof von Block a?
            for i_id in bahnhof_ids:
                xi_ia[(i_id, a_id)] = 1 if i_id == blk.origin_yard_id else 0

        A_ids = [b.block_id for b in block_objekte]
        print(f"Graph erstellt: {len(A_ids)} logische Blöcke.")

        # --- 3. PFADSUCHE (Q) ---
        print(f"Suche Top-{anzahl_pfade} Blocking-Pfade pro Auftrag...")
        
        path_counter = 0
        for k in auftrags_liste:
            k_id = k.order_id
            
            # Pfadsuche im Block-Graphen
            paths_found = _finde_top_k_blocking_pfade(
                k.origin, k.destination, anzahl_pfade, block_graph_adj, bahnhof_map
            )
            
            path_ids_for_k = []
            
            if not paths_found:
                print(f"WARNUNG: Kein Pfad für {k_id} ({k.origin}->{k.destination}) gefunden!")
                continue

            for p_blocks in paths_found:
                q_id = f"P{path_counter}"
                path_counter += 1
                path_ids_for_k.append(q_id)
                
                # Speichere die Block-Sequenz für spätere Analysen
                Pfad_Definitionen[q_id] = p_blocks
                
                # Kosten C_kq berechnen
                cost_val = 0
                block_ids_in_path = set()
                for blk in p_blocks:
                    # Kosten = Block-Fahrzeit + Rangierzeit am Start des Blocks
                    cost_val += t_a[blk.block_id] + w_a[blk.block_id]
                    block_ids_in_path.add(blk.block_id)
                
                C_kq[(k_id, q_id)] = cost_val
                
                # Delta Parameter: Welche Blöcke 'a' sind im Pfad 'q' enthalten?
                for a_x in A_ids:
                    delta_kqa[(k_id, q_id, a_x)] = 1 if a_x in block_ids_in_path else 0
            
            Qk[k_id] = path_ids_for_k
            
            # Weitere Parameter
            d_k[k_id] = k.anzahl_waggons
            T_k[k_id] = k.latest_arrival_time

        # Stations-Parameter
        for bhf in bahnhof_liste:
            V_i[bhf.yard_id] = bhf.kapazitaet
            N_i[bhf.yard_id] = bhf.dispatch_kapazität

        # 4. Rückgabe
        print("Datenverarbeitung abgeschlossen.")
        
        return SimpleNamespace(
            S = bahnhof_ids,
            A = A_ids,
            K = list(d_k.keys()),
            
            Qk = Qk,
            d_k = d_k,
            T_k = T_k,
            
            C_kq = C_kq,
            
            t_a = t_a,
            w_a = w_a,
            chi_a = chi_a,
            u_a = u_a,
            
            V_i = V_i,
            N_i = N_i,
            
            delta_kqa = delta_kqa,
            xi_ia = xi_ia,
            
            # Zusatzinfos für Auswertung
            obj_bloecke = {b.block_id: b for b in block_objekte},
            obj_pfade = Pfad_Definitionen
        )

    except Exception as e:
        print(f"SCHWERER FEHLER beim Laden: {e}")
        import traceback
        traceback.print_exc()
        return None