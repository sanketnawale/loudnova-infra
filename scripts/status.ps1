$ErrorActionPreference = "Stop"
kubectl get nodes -o wide
kubectl get pods -A
kubectl get services -A
kubectl get ingress -A