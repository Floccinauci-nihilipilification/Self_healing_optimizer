# CorteX — Autonomous Chaos Engineering & Self-Healing Platform

> Built for **Tech Solstice PS1** — a 36-hour hackathon at Manipal Academy of Higher Education.

An end-to-end, production-grade platform that autonomously injects failures into a live Kubernetes microservice application, detects anomalies using machine learning on real telemetry, and self-heals without any human intervention.

---

## Overview

Modern distributed systems fail in unpredictable ways. Human operators are too slow — detection and recovery can take 15–30 minutes. CorteX brings that down to **under 15 seconds**, autonomously.

The platform runs a full chaos engineering loop: inject failure → detect anomaly via ML → execute healing action → verify recovery. Every step is automated and observable in real time through a live SRE dashboard.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    CorteX Platform                        │
│                                                          │
│  Chaos Mesh ──► Online Boutique (11 microservices)      │
│      ↓                    ↓                             │
│  Injects failure    Prometheus scrapes metrics           │
│                           ↓                             │
│               FastAPI ML API (Isolation Forest)          │
│                           ↓                             │
│              Kopf Operator detects + heals               │
│                           ↓                             │
│           React SRE Dashboard (live view)                │
└─────────────────────────────────────────────────────────┘
```

**Recovery time: ~15 seconds. Zero human intervention.**

---

## Tech Stack

| Layer | Technology |
|---|---|
| Kubernetes cluster | Minikube (Docker driver) |
| Victim application | Google Online Boutique (11 microservices) |
| Chaos injection | Chaos Mesh |
| Telemetry | Prometheus + Grafana (kube-prometheus-stack) |
| ML anomaly detection | FastAPI + Scikit-Learn Isolation Forest |
| Self-healing operator | Python + Kopf (Kubernetes Operator Framework) |
| SRE dashboard | React + Recharts + Tailwind CSS |
| Dashboard backend | FastAPI (bridges React ↔ Prometheus ↔ ML) |

All core infrastructure components are CNCF graduated or incubating projects.

---

## Repository Structure

```
Self_healing_optimizer/
├── intelligence-stack/
│   ├── ml-api/
│   │   ├── main.py              # FastAPI inference server
│   │   ├── train_model.py       # Isolation Forest trainer
│   │   ├── isolation_forest.joblib
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── dashboard-ui/
│       ├── api.py               # FastAPI dashboard backend
│       ├── dashboard.py         # Streamlit dashboard (legacy)
│       ├── Dockerfile
│       └── sre-dashboard/       # React SRE dashboard
│           └── src/
│               ├── App.jsx      # Main dashboard component
│               └── index.css
├── k8s-infrastructure/
│   ├── chaos-scenarios/
│   │   ├── cpu-stress.yaml      # 80% CPU on frontend
│   │   ├── memory-stress.yaml   # 256MB RAM on cartservice
│   │   ├── pod-kill.yaml        # Kill frontend pod
│   │   ├── network-delay.yaml   # 200ms latency injection
│   │   └── http-abort.yaml      # 100% packet loss
│   ├── operator-healer/
│   │   ├── operator.py          # Kopf self-healing operator
│   │   ├── deploy.yaml          # Operator Kubernetes deployment
│   │   ├── rbac.yaml            # RBAC permissions
│   │   ├── ml-api-deploy.yaml   # ML API Kubernetes deployment
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── target-app/
│       └── online-boutique.yaml
└── README.md
```

---

## How It Works

### 1. Chaos Injection
Chaos Mesh injects real failures into the cluster using Kubernetes-native CRDs. Four experiment types are supported: CPU stress, memory pressure, pod kill, and network disruption.

### 2. Telemetry Collection
Prometheus scrapes CPU usage, memory consumption, and latency from all 11 microservices every 15 seconds. Grafana visualizes the data in real time.

### 3. ML Anomaly Detection
A Scikit-Learn Isolation Forest model (200 estimators) trained on synthetic telemetry data covering three failure scenarios — CPU spike, OOM pressure, and network partition — analyzes incoming metrics and returns:
- `is_anomaly` — boolean
- `threat_score` — float between 0 and 1
- `recommended_action` — one of `RESTART_POD`, `SCALE_OUT_HPA`, `FLUSH_REDIS_CACHE`, `REROUTE_TRAFFIC`

### 4. Self-Healing Operator
A custom Kubernetes operator built with Kopf watches all pods in the `applications` namespace. On detecting a pod phase change or crash loop, it queries Prometheus for live metrics, sends them to the ML API, and executes the recommended healing action automatically.

### 5. SRE Dashboard
A React dashboard provides a single pane of glass: live application iframe, microservice topology map, real-time metrics charts, ML analysis panel, chaos lifecycle tracker, and one-click chaos injection buttons.

---

## Healing Actions

| Condition | Action |
|---|---|
| Threat score < 0.4 | No action |
| CPU > 85% | Scale out (HPA) |
| Memory > 85% | Flush Redis cache |
| Latency > 2000ms | Reroute traffic |
| Threat score > 0.8 | Restart pod |

---

## Setup & Running

### Prerequisites
- Docker Desktop
- Minikube
- kubectl
- Helm
- Node.js 18+
- Python 3.11+

### 1. Start the cluster

```bash
minikube start --cpus 4 --memory 6144 --driver=docker
```

### 2. Create namespaces

```bash
kubectl create namespace applications
kubectl create namespace monitoring
kubectl create namespace chaos-testing
```

### 3. Deploy Online Boutique

```bash
kubectl apply -f k8s-infrastructure/target-app/online-boutique.yaml -n applications
```

### 4. Install Prometheus + Grafana

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install prometheus prometheus-community/kube-prometheus-stack -n monitoring
```

### 5. Install Chaos Mesh

```bash
helm repo add chaos-mesh https://charts.chaos-mesh.org
helm repo update
helm install chaos-mesh chaos-mesh/chaos-mesh -n chaos-testing \
  --set chaosDaemon.runtime=docker \
  --set chaosDaemon.socketPath=/var/run/docker.sock
```

### 6. Build and deploy the ML API

```bash
cd intelligence-stack/ml-api
minikube docker-env | Invoke-Expression   # Windows PowerShell
docker build --platform linux/amd64 -t ml-api:latest .
kubectl apply -f k8s-infrastructure/operator-healer/ml-api-deploy.yaml
```

### 7. Build and deploy the Kopf operator

```bash
cd k8s-infrastructure/operator-healer
minikube docker-env | Invoke-Expression
docker build --platform linux/amd64 -t self-healer-operator:latest .
kubectl apply -f rbac.yaml
kubectl apply -f deploy.yaml
```

### 8. Start port-forwards (one terminal each)

```bash
kubectl port-forward svc/prometheus-kube-prometheus-prometheus 9090:9090 -n monitoring
kubectl port-forward svc/prometheus-grafana 3000:80 -n monitoring
kubectl port-forward svc/ml-api-service 8000:8000
kubectl port-forward svc/frontend 8888:80 -n applications
minikube service frontend -n applications
```

### 9. Start the dashboard backend

```bash
cd intelligence-stack/dashboard-ui
pip install fastapi uvicorn httpx pydantic
python api.py
```

### 10. Start the React dashboard

```bash
cd intelligence-stack/dashboard-ui/sre-dashboard
npm install
npm run dev
```

Open `http://localhost:5173` to access the CorteX SRE dashboard.

---

## Demo Flow

1. Open the dashboard — Online Boutique loads live in the iframe
2. Open Grafana at `http://localhost:3000` — metrics are flowing
3. Click **Kill Frontend** in the chaos panel — frontend scales to 0, real 503 appears in iframe
4. Watch the ML threat score spike in the dashboard
5. Watch the Kopf operator logs show `ANOMALY DETECTED → RESTART_POD`
6. After ~15 seconds, the site automatically recovers in the iframe
7. Auto-Heals counter increments — zero human intervention

---

## Chaos Experiments

Apply any experiment manually:

```bash
kubectl apply -f k8s-infrastructure/chaos-scenarios/pod-kill.yaml
kubectl apply -f k8s-infrastructure/chaos-scenarios/cpu-stress.yaml
kubectl apply -f k8s-infrastructure/chaos-scenarios/memory-stress.yaml
kubectl apply -f k8s-infrastructure/chaos-scenarios/network-delay.yaml
```

Delete to stop:

```bash
kubectl delete -f k8s-infrastructure/chaos-scenarios/pod-kill.yaml
```

---

## Team

Built in 36 hours at Tech Solstice — Manipal Academy of Higher Education.

| Role | Scope |
|---|---|
| Platform / SRE Engineer | Minikube, Helm, Kubernetes manifests, Chaos Mesh, Kopf operator |
| ML / UI Engineer | FastAPI ML model, Isolation Forest, React dashboard, Streamlit |

---

## CNCF Compliance

All infrastructure components are from the CNCF ecosystem:

- **Kubernetes** — graduated
- **Prometheus** — graduated
- **Helm** — graduated
- **Chaos Mesh** — incubating
