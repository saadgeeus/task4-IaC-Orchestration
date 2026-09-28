# Task 4: Automated Infrastructure as Code & Orchestration Architecture

**Project:** flask_app123
**Environment:** AWS EC2 (Ubuntu) + Minikube (Docker driver)
**Tools:** Terraform, Docker, Kubernetes, NGINX Ingress, Metrics Server

---

## 1. Objective

Provision and orchestrate an elastic, highly available microservices environment by:

1. Defining an isolated cloud network with **Infrastructure as Code (Terraform)**.
2. Containerizing the Flask application with **Docker**.
3. Deploying it on a **Kubernetes** cluster with a **Persistent Volume Claim**, an **Ingress controller** and a **Horizontal Pod Autoscaler (HPA)**.

---

## 2. Architecture

```
                    Internet
                       |
              AWS EC2 Public IP :8080
                       |
              kubectl port-forward
                       |
        +--------------+---------------+
        |          Minikube            |
        |                              |
        |   Ingress (nginx) --> Service (ClusterIP :80)
        |                              |
        |                +-------------+-------------+
        |                |             |             |
        |              Pod 1         Pod 2     ...  Pod N   <-- HPA (2 to 6)
        |                \             |             /
        |                 +--- PVC (1Gi, /app/data) --+
        +------------------------------+
```

AWS network layer (Terraform): VPC, public subnet, Internet Gateway, route table and security group.

---

## 3. Repository Structure

```
flask_app123/
├── app.py
├── requirements.txt
├── Dockerfile
├── terraform/
│   └── main.tf
├── k8s/
│   ├── pvc.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml
│   └── hpa.yaml
└── README.md
```

---

## 4. What Was Done

### Step 1: Environment setup on EC2

An EC2 instance (recommended `t2.medium` or higher) was launched and the following tools were installed:

| Tool | Purpose |
|------|---------|
| Docker | Build and run container images |
| kubectl | Kubernetes command line client |
| Minikube | Local single-node Kubernetes cluster |
| Terraform | Infrastructure as Code |

Minikube was started with the Docker driver:

```bash
minikube start --driver=docker --cpus=2 --memory=3900
minikube addons enable ingress
minikube addons enable metrics-server
```

The `ingress` addon provides the NGINX Ingress controller. The `metrics-server` addon is required so the HPA can read CPU usage.

### Step 2: Containerizing the application

The Flask application was packaged with a Dockerfile:

```bash
docker build -t flask_app123:v1 .
minikube image load flask_app123:v1
```

`minikube image load` was needed because Minikube uses its own Docker daemon. The Deployment uses `imagePullPolicy: Never` so Kubernetes uses this local image.

### Step 3: Network provisioning with Terraform

Terraform (`terraform/main.tf`) declaratively creates the isolated network in AWS `us-east-1`:

| Resource | Details |
|----------|---------|
| `aws_vpc` | CIDR `10.0.0.0/16`, DNS support enabled |
| `aws_subnet` | Public subnet `10.0.1.0/24` in `us-east-1a` |
| `aws_internet_gateway` | Gives the VPC internet access |
| `aws_route_table` + association | Routes `0.0.0.0/0` through the Internet Gateway |
| `aws_security_group` | Allows inbound HTTP (port 80), all outbound |

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

### Step 4: Kubernetes deployment

All manifests are in the `k8s/` folder.

| Manifest | What it does |
|----------|--------------|
| `pvc.yaml` | Requests 1Gi of persistent storage (`ReadWriteOnce`) so data survives pod restarts |
| `deployment.yaml` | Runs 2 replicas of `flask_app123:v1`, CPU request 100m / limit 250m, mounts the PVC at `/app/data` |
| `service.yaml` | ClusterIP Service exposing port 80 and forwarding to the container |
| `ingress.yaml` | NGINX Ingress routing host `flaskapp.local` to the Service |
| `hpa.yaml` | Scales the Deployment between 2 and 6 replicas at 50% average CPU |

```bash
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml
kubectl apply -f k8s/hpa.yaml
```

### Step 5: Verification

```bash
kubectl get pods,svc,pvc,ingress,hpa
minikube ip
curl -H "Host: flaskapp.local" http://$(minikube ip)
```

### Step 6: External browser access

Minikube with the Docker driver does not expose the Ingress on the EC2 host port directly, so the Service was exposed with port-forward:

```bash
nohup kubectl port-forward --address 0.0.0.0 svc/flask-service 8080:80 > pf.log 2>&1 &
```

Port **8080** was then allowed in the EC2 Security Group inbound rules, and the app was opened in a browser at:

```
http://<EC2-PUBLIC-IP>:8080
```

---

## 5. Testing

### 5.1 Horizontal Pod Autoscaler

Terminal 1 watches the HPA:

```bash
kubectl get hpa flask-hpa -w
```

Terminal 2 generates load:

```bash
kubectl run -i --tty load-generator --rm --image=busybox --restart=Never -- \
  /bin/sh -c "while true; do wget -q -O- http://flask-service; done"
```

Result: CPU utilization rose above the 50% target and the replica count increased from 2 towards the maximum of 6. After the load stopped, replicas scaled back down to 2.

### 5.2 Persistent volume

```bash
kubectl exec deployment/flask-app -- sh -c "echo 'persistent data' > /app/data/test.txt"
kubectl delete pod -l app=flask-app
kubectl exec deployment/flask-app -- cat /app/data/test.txt
```

Result: the file remained available after the pod was recreated, confirming the PVC works.

---

## 6. Issues Faced and Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| `curl flaskapp.local` failed to connect | Hostname pointed to `127.0.0.1`, but nothing listens on host port 80 (Minikube Docker driver) | Point `/etc/hosts` to `$(minikube ip)` and test with `curl -H "Host: flaskapp.local" http://$(minikube ip)` |
| Container port mismatch risk | `containerPort` / `targetPort` must match the port the app really listens on | Verified the app port with `kubectl logs` and set `containerPort` and `targetPort` accordingly (80 in this setup) |
| App not reachable from outside EC2 | Ingress is only reachable inside the EC2 host | Used `kubectl port-forward --address 0.0.0.0` and opened port 8080 in the Security Group |
| Docker permission denied | User not in `docker` group | `sudo usermod -aG docker $USER` and re-login (`newgrp docker`) |

---

## 7. Screenshots

Add screenshots to a `screenshots/` folder and link them here.

| Evidence | File |
|----------|------|
| Terraform apply complete | `screenshots/terraform-apply.jpg` |
| Terraform apply complete VPC-AWS | `screenshots/terraform-aws.jpg` |
| Docker image built | `screenshots/docker-images.jpg` |
| `kubectl get pods,svc,pvc,ingress,hpa` | `screenshots/kubectl-services-SS.jpg` |
| App in browser (EC2 IP visible) | `screenshots/port-maping-SS.jpg` |
| HPA scaling under load | `screenshots/check-HPA-replicas.jpg` |
| Docker-App Live Debugger | `screenshots/live-debug.jpg` |

---

## 8. Cleanup

```bash
cd terraform && terraform destroy
minikube stop
pkill -f "port-forward"
```

Also stop the EC2 instance when it is not in use to avoid extra AWS charges.

---

## 9. Key Learnings

- Infrastructure can be described as code with Terraform, making it repeatable and version controlled.
- A PersistentVolumeClaim separates storage from the pod lifecycle, so data survives restarts.
- An Ingress controller provides a single entry point and host based routing to Services.
- An HPA needs resource requests and a working metrics server to scale pods automatically on CPU load.
- Networking details of the local cluster driver (Minikube Docker driver) affect how services are reached from outside the host.
