import json
import random
import heapq
import math

# Konfigurtion
QUELLE_DATEI = 'RandomizedInstances/24Horizon-1Discretization-40Orders.json' # Ihre Basis-Datei
SCENARIO_SIZE = 1000  # <-- HIER ÄNDERN: Anzahl der Aufträge
AUSGABE_DATEI = f'Instance_{SCENARIO_SIZE}.json'

# PH = 1 Woche
PLANUNGSHORIZONT = 168        # Stunden

# Hub-Definition 
HUB_PARAMS = {
    "rangier_dauer": 4,       # Stunden
    "kapazitaet_wagen": 5000, # Wagen pro Woche
    "kapazitaet_zuege": 200,  # Züge pro Woche
    "kosten_pro_wagen": 15.0 
}

SAT_PARAMS = {
    "rangier_dauer": 8,       
    "kapazitaet_wagen": 2500,  
    "kapazitaet_zuege": 70,   
    "kosten_pro_wagen": 25.0  
}

TRAIN_PARAMS = {
    "max_length": 700.0,      # Meter
    "max_weight": 1200.0,     # Tonnen
    "capacity_cars": 30       # Wagen pro Zug
}

# Hilfsfunktionen

def dijkstra_duration(start_node, end_node, graph):
    """Berechnet die mindeste Fahrzeit zwischen zwei Knoten für realistische Deadlines."""
    pq = [(0, start_node)]
    visited = {}
    
    while pq:
        curr_dur, curr_node = heapq.heappop(pq)
        
        if curr_node == end_node:
            return curr_dur
        
        if curr_node in visited and visited[curr_node] <= curr_dur:
            continue
        visited[curr_node] = curr_dur
        
        for neighbor, edge_dur in graph.get(curr_node, []):
            new_dur = curr_dur + edge_dur
            if neighbor not in visited or new_dur < visited[neighbor]:
                heapq.heappush(pq, (new_dur, neighbor))
                
    return 999999 # Fallback

def main():
    print(f"Starte Generierung: {SCENARIO_SIZE} Aufträge")
    
    # 1. Lade Originalstruktur
    try:
        with open(QUELLE_DATEI, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
    except FileNotFoundError:
        print(f"FEHLER: Datei '{QUELLE_DATEI}' nicht gefunden.")
        return

    # 2. Analysiere Netzwerk & Identifiziere Hubs
    adjacency = {}
    yards_raw = {}
    
    # Lese Bahnhöfe
    for node in raw_data['Network']['Nodes']['YardNodes']:
        y_id = node['ShuntingYard']['YardId']['Value']
        if y_id not in yards_raw:
            yards_raw[y_id] = node['ShuntingYard'] 
            adjacency[y_id] = []

    # Lese Kanten & baue Nachbarschaft
    physical_arcs = []
    seen_arcs = set()
    
    for arc in raw_data['Network']['Arcs']['DrivingArcs']:
        src = arc['YardFrom']['ShuntingYard']['YardId']['Value']
        dst = arc['YardTo']['ShuntingYard']['YardId']['Value']
        dur = arc['Duration']['Value'] 
        
        if src == dst: continue
        
        adjacency[src].append((dst, dur))
        
        if (src, dst) not in seen_arcs:
            seen_arcs.add((src, dst))
            
            new_arc = {
                "YardFrom": {"ShuntingYard": {"YardId": {"Value": src}}},
                "YardTo":   {"ShuntingYard": {"YardId": {"Value": dst}}},
                "Duration": {"Value": dur}, 
                "MaximalTrainLength": {"Value": TRAIN_PARAMS['max_length']},
                "MaximalTrainWeight": {"Value": TRAIN_PARAMS['max_weight']}
            }
            physical_arcs.append(new_arc)

    # Hub-Erkennung (Top 3 nach Verbindungen)
    sorted_yards = sorted(adjacency.keys(), key=lambda k: len(adjacency[k]), reverse=True)
    hubs = set(sorted_yards[:3]) 
    print(f"Identifizierte Hubs (für Parameter): {hubs}")

    # 3. Erstelle finalen Bahnhofs-Datensatz
    final_nodes = []
    for y_id in yards_raw.keys():
        is_hub = y_id in hubs
        params = HUB_PARAMS if is_hub else SAT_PARAMS
        
        node_obj = {
            "NodeId": {"Value": y_id}, 
            "ShuntingYard": {
                "YardId": {"Value": y_id},
                "ShuntingDuration": {"Value": params['rangier_dauer']},
                "FreightCarCapacity": {"Value": params['kapazitaet_wagen']},
                "ShuntingCostPerCar": {"Cost": {"Value": params['kosten_pro_wagen']}},
                "TrainDispatchCapacity": {"Value": params['kapazitaet_zuege']}
            },
            "ActualTime": {"Value": 0} 
        }
        final_nodes.append(node_obj)

    # 4. Aufträge Generieren 
    orders = []
    yard_ids = list(yards_raw.keys())
    
    print("Generiere Aufträge...")
    
    for i in range(1, SCENARIO_SIZE + 1):
        order_id = f"Ord_{i}"
        
        # Zufälliger Start und Ziel (ungleich)
        o = random.choice(yard_ids)
        d = random.choice(yard_ids)
        while o == d:
            d = random.choice(yard_ids)
            
        # Zufällige Wagenanzahl (einheitlicher Bereich für alle)
        # zwischen 1 und 20 Wagen
        cars = random.randint(1, 20)

        # Bestimme Mindestfahrzeit (Dijkstra) für Deadline
        min_travel_time = dijkstra_duration(o, d, adjacency)
        
        # Zeitfenster: Mindestens Fahrzeit + Puffer
        buffer = 24         # Stunden Puffer
        max_time = min_travel_time + buffer
        
        # Parameter berechnen
        weight = cars * 25.0 
        length = cars * 18.0 
        
        new_order = {
            "OrderId": {"Value": order_id},
            "Origin": {"ShuntingYard": {"YardId": {"Value": o}}},
            "Destination": {"ShuntingYard": {"YardId": {"Value": d}}},
            "NumberOfFreightCars": {"Value": cars},
            "OrderWeight": {"Value": weight},
            "OrderLength": {"Value": length},
            "ReadyTime": {"Value": 0},
            "MaxTimeUntilArrival": {"Value": max_time}
        }
        orders.append(new_order)

    # 5. Speichern
    final_json = {
        "Network": {
            "Nodes": {
                "YardNodes": final_nodes,
                "Count": len(final_nodes)
            },
            "Arcs": {
                "DrivingArcs": physical_arcs,
                "Count": len(physical_arcs)
            }
        },
        "Orders": orders
    }
    
    with open(AUSGABE_DATEI, 'w', encoding='utf-8') as f:
        json.dump(final_json, f, indent=None)

    print(f"--- Fertig! ---")
    print(f"Datei: {AUSGABE_DATEI}")
    print(f"Aufträge: {len(orders)}")

if __name__ == "__main__":
    main()