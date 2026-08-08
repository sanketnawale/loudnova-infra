# LoudNova Home Platform

Production-style Kubernetes repository for the LoudNova home server.

## Current platform

- Ubuntu Server 26.04 LTS
- Single-node K3s
- Tailscale private administration
- Traefik ingress
- K3s ServiceLB
- Kustomize-managed workloads

## Connect

`powershell
$env:KUBECONFIG="$HOME\.kube\loudnova.yaml"
kubectl config use-context loudnova-home
kubectl get nodes
`

## Validate

`powershell
.\scripts\validate.ps1
`

## Deploy

`powershell
.\scripts\deploy.ps1
`
"@

Write-File "clusters\loudnova\platform\kustomization.yaml" @"
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - namespaces