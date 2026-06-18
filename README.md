# Payment Ninja — Project 1: EKS GitOps Platform

A production-style deployment of a Flask microservice using Docker, Kubernetes, Helm, and ArgoCD with autoscaling.

---

## What This Project Does

```
You push code to GitHub
        ↓
ArgoCD detects the change
        ↓
Automatically deploys to Kubernetes
        ↓
HPA scales pods based on CPU
```

---

## Project Structure

```
payment-ninja-gitops/
├── app.py                          # Flask application
├── Dockerfile                      # Docker image definition
├── requirements.txt                # Python dependencies
├── deployment.yaml                 # Raw K8s deployment (reference)
├── service.yaml                    # Raw K8s service (reference)
├── hpa.yaml                        # HorizontalPodAutoscaler
└── payment-ninja/                  # Helm chart
    ├── Chart.yaml
    ├── values.yaml                 # Default values (dev)
    └── templates/
        ├── deployment.yaml         # Helm deployment template
        └── service.yaml            # Helm service template
```

---

## Tech Stack

| Tool | Purpose |
|------|---------|
| Flask | Python web app (payment-service) |
| Docker | Containerize the app |
| kind | Local Kubernetes cluster |
| kubectl | Interact with cluster |
| Helm | Package and deploy app |
| ArgoCD | GitOps — auto deploy from GitHub |
| HPA | Auto scale pods based on CPU |
| metrics-server | Provides CPU/memory metrics to HPA |

---

## Step by Step — What We Did

### Step 1 — Flask App

Created a simple Flask app with 2 routes:

```python
from flask import Flask
app = Flask(__name__)

@app.route("/")
def home():
    return "welcome to home page"

@app.route("/payment")
def payment():
    return "payment done"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
```

Run locally:
```bash
python3 app.py
```

---

### Step 2 — Dockerize

Created `Dockerfile`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "app.py"]
```

Build and run:
```bash
docker build -t payment-ninja:v1 .
docker run -d -p 80:5000 --name payment-ninja payment-ninja:v1
```

Test:
```bash
curl http://localhost:80
curl http://localhost:80/payment
```

---

### Step 3 — Create Kind Cluster

```bash
kind create cluster --name payment-ninja
kubectl get nodes
```

Load Docker image into kind (kind can't access local Docker images directly):
```bash
kind load docker-image payment-ninja:v1 --name payment-ninja
```

---

### Step 4 — Create Namespaces

```bash
kubectl create namespace dev
kubectl create namespace prod
kubectl get ns
```

---

### Step 5 — Deploy with Raw Kubernetes YAML

`deployment.yaml`:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-ninja
  namespace: dev
spec:
  replicas: 2
  selector:
    matchLabels:
      app: payment-ninja
  template:
    metadata:
      labels:
        app: payment-ninja
    spec:
      containers:
      - name: payment-ninja
        image: payment-ninja:v1
        ports:
        - containerPort: 5000
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 200m
            memory: 256Mi
```

`service.yaml`:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: payment-ninja-svc
spec:
  selector:
    app: payment-ninja
  ports:
  - port: 80
    targetPort: 5000
  type: NodePort
```

Apply:
```bash
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl get pods -n dev
kubectl get svc -n dev
```

Access app:
```bash
kubectl port-forward svc/payment-ninja-svc 8000:80 &
curl http://localhost:8000
```

---

### Step 6 — Package with Helm

Create Helm chart:
```bash
helm create payment-ninja
```

Clean default templates:
```bash
rm payment-ninja/templates/*
rm -rf payment-ninja/templates/tests
```

`payment-ninja/templates/deployment.yaml`:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .Values.appName }}
  namespace: {{ .Values.namespace }}
spec:
  replicas: {{ .Values.replicas }}
  selector:
    matchLabels:
      app: {{ .Values.appName }}
  template:
    metadata:
      labels:
        app: {{ .Values.appName }}
    spec:
      containers:
      - name: {{ .Values.appName }}
        image: {{ .Values.image }}:{{ .Values.tag }}
        ports:
        - containerPort: {{ .Values.port }}
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 200m
            memory: 256Mi
```

`payment-ninja/values.yaml`:
```yaml
appName: payment-ninja
namespace: dev
replicas: 2
image: payment-ninja
tag: v1
port: 5000
```

Deploy to dev:
```bash
helm install payment-ninja ./payment-ninja -n dev
```

Deploy to prod (different values, same chart):
```bash
helm install payment-ninja-prod ./payment-ninja \
  --set namespace=prod \
  --set replicas=3 \
  -n prod
```

---

### Step 7 — GitOps with ArgoCD

Install ArgoCD:
```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

Wait for pods:
```bash
kubectl get pods -n argocd
```

Access UI:
```bash
kubectl port-forward svc/argocd-server -n argocd 8085:443 &
```

Get password:
```bash
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
```

Open: `https://localhost:8085`
- Username: `admin`
- Password: (from above)

Create ArgoCD App:
```
Application Name: payment-ninja
Project: default
Sync Policy: Automatic
Repository URL: https://github.com/sanmathik8/payment-ninja-gitops
Revision: main
Path: payment-ninja
Cluster URL: https://kubernetes.default.svc
Namespace: dev
```

Test GitOps — change replicas in values.yaml and push:
```bash
# Edit payment-ninja/values.yaml → replicas: 4
git add .
git commit -m "scale to 4 replicas"
git push
# ArgoCD auto syncs within 3 minutes!
```

---

### Step 8 — HPA (Horizontal Pod Autoscaler)

Install metrics-server:
```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl patch deployment metrics-server -n kube-system --type='json' -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
```

`hpa.yaml`:
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: payment-ninja-hpa
  namespace: dev
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: payment-ninja
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 50
```

Apply:
```bash
kubectl apply -f hpa.yaml
kubectl get hpa -n dev
kubectl top pods -n dev
```

---

## Key Commands Reference

```bash
# Cluster
kind create cluster --name payment-ninja
kind load docker-image payment-ninja:v1 --name payment-ninja
kubectl get nodes

# Pods
kubectl get pods -n dev
kubectl get pods -n prod
kubectl top pods -n dev

# Helm
helm install payment-ninja ./payment-ninja -n dev
helm upgrade payment-ninja ./payment-ninja -n dev
helm list -n dev

# ArgoCD
kubectl get pods -n argocd
kubectl port-forward svc/argocd-server -n argocd 8085:443 &

# HPA
kubectl get hpa -n dev
kubectl describe hpa payment-ninja-hpa -n dev
```

---

## Exercises Covered

| Exercise | Description | Status |
|----------|-------------|--------|
| Ex 1 | EKS app deployment via GitOps | ✅ |
| Ex 16 | EKS cluster (kind locally) | ✅ |
| Ex 18 | GitOps with ArgoCD | ✅ |
| Ex 19 | Helm chart engineering | ✅ |
| Ex 22 | HPA autoscaling | ✅ |

---
rver
