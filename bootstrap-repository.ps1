$ErrorActionPreference = "Stop"

$Root = (Get-Location).Path

function Write-File {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string]$Content
    )
    $fullPath = Join-Path $Root $Path
    $parent = Split-Path -Parent $fullPath
    if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    [System.IO.File]::WriteAllText($fullPath, $Content, [System.Text.UTF8Encoding]::new($false))
}

$directories = @(
    "clusters\loudnova\platform\namespaces",
    "clusters\loudnova\platform\networking\traefik",
    "clusters\loudnova\platform\networking\envoy-gateway",
    "clusters\loudnova\apps\hello-web\base",
    "clusters\loudnova\apps\hello-web\overlays\home",
    "terraform\platform",
    "scripts",
    "docs"
)
foreach ($directory in $directories) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Root $directory) | Out-Null
}

Write-File ".gitignore" @"
# Terraform
**/.terraform/*
*.tfstate
*.tfstate.*
*.tfplan

# Kubernetes credentials
kubeconfig
*.kubeconfig
*.kubeconfig.yaml

# Secrets
*.secret.yaml
*.secrets.yaml
.env
.env.*

# Keys and certificates
*.key
*.pem
*.p12
*.pfx

# Editors and OS
.vscode/
.idea/
.DS_Store
Thumbs.db

# Temporary files
*.tmp
*.bak
*.log
"@

Write-File "README.md" @"
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

```powershell
`$env:KUBECONFIG="`$HOME\.kube\loudnova.yaml"
kubectl config use-context loudnova-home
kubectl get nodes
```

## Validate

```powershell
.\scripts\validate.ps1
```

## Deploy

```powershell
.\scripts\deploy.ps1
```
"@

Write-File "clusters\loudnova\platform\kustomization.yaml" @"
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - namespaces
"@

Write-File "clusters\loudnova\platform\namespaces\kustomization.yaml" @"
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources: []
"@

Write-File "clusters\loudnova\platform\networking\traefik\README.md" @"
# Traefik

Traefik is currently installed and managed by K3s.
"@

Write-File "clusters\loudnova\platform\networking\envoy-gateway\README.md" @"
# Envoy Gateway

Reserved for the future migration from Traefik to Envoy Gateway.
"@

Write-File "clusters\loudnova\apps\hello-web\base\namespace.yaml" @"
apiVersion: v1
kind: Namespace
metadata:
  name: hello-web
  labels:
    app.kubernetes.io/part-of: loudnova-websites
    app.kubernetes.io/managed-by: kustomize
"@

Write-File "clusters\loudnova\apps\hello-web\base\configmap.yaml" @"
apiVersion: v1
kind: ConfigMap
metadata:
  name: hello-web-content
  namespace: hello-web
data:
  index.html: |
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>LoudNova Kubernetes</title>
      </head>
      <body>
        <h1>Hello from LoudNova</h1>
        <p>Your K3s website is managed from the local repository.</p>
      </body>
    </html>
"@

Write-File "clusters\loudnova\apps\hello-web\base\deployment.yaml" @"
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hello-web
  namespace: hello-web
  labels:
    app.kubernetes.io/name: hello-web
spec:
  replicas: 1
  revisionHistoryLimit: 3
  selector:
    matchLabels:
      app.kubernetes.io/name: hello-web
  template:
    metadata:
      labels:
        app.kubernetes.io/name: hello-web
    spec:
      automountServiceAccountToken: false
      securityContext:
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: nginx
          image: nginx:1.29-alpine
          ports:
            - name: http
              containerPort: 80
          resources:
            requests:
              cpu: 10m
              memory: 16Mi
            limits:
              cpu: 100m
              memory: 64Mi
          readinessProbe:
            httpGet:
              path: /
              port: http
            initialDelaySeconds: 3
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /
              port: http
            initialDelaySeconds: 10
            periodSeconds: 10
          volumeMounts:
            - name: website-content
              mountPath: /usr/share/nginx/html
              readOnly: true
      volumes:
        - name: website-content
          configMap:
            name: hello-web-content
"@

Write-File "clusters\loudnova\apps\hello-web\base\service.yaml" @"
apiVersion: v1
kind: Service
metadata:
  name: hello-web
  namespace: hello-web
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: hello-web
  ports:
    - name: http
      port: 80
      targetPort: http
"@

Write-File "clusters\loudnova\apps\hello-web\base\ingress.yaml" @"
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: hello-web
  namespace: hello-web
spec:
  ingressClassName: traefik
  rules:
    - http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: hello-web
                port:
                  name: http
"@

Write-File "clusters\loudnova\apps\hello-web\base\kustomization.yaml" @"
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - namespace.yaml
  - configmap.yaml
  - deployment.yaml
  - service.yaml
  - ingress.yaml
labels:
  - pairs:
      environment: home
    includeSelectors: false
"@

Write-File "clusters\loudnova\apps\hello-web\overlays\home\kustomization.yaml" @"
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../base
replicas:
  - name: hello-web
    count: 1
"@

Write-File "scripts\validate.ps1" @"
`$ErrorActionPreference = "Stop"
`$expectedContext = "loudnova-home"
`$currentContext = kubectl config current-context
if (`$currentContext -ne `$expectedContext) { throw "Wrong Kubernetes context: `$currentContext. Expected: `$expectedContext" }
kubectl get nodes
kubectl kustomize .\clusters\loudnova\platform | Out-Null
kubectl kustomize .\clusters\loudnova\apps\hello-web\overlays\home | Out-Null
kubectl apply -k .\clusters\loudnova\apps\hello-web\overlays\home --dry-run=server
Write-Host "Validation completed successfully."
"@

Write-File "scripts\deploy.ps1" @"
`$ErrorActionPreference = "Stop"
`$expectedContext = "loudnova-home"
`$currentContext = kubectl config current-context
if (`$currentContext -ne `$expectedContext) { throw "Wrong Kubernetes context: `$currentContext. Expected: `$expectedContext" }
kubectl apply -k .\clusters\loudnova\platform
kubectl apply -k .\clusters\loudnova\apps\hello-web\overlays\home
kubectl rollout status deployment/hello-web --namespace hello-web --timeout=180s
kubectl get pods,svc,ingress -n hello-web
"@

Write-File "scripts\status.ps1" @"
`$ErrorActionPreference = "Stop"
kubectl get nodes -o wide
kubectl get pods -A
kubectl get services -A
kubectl get ingress -A
"@

Write-File "scripts\destroy-hello.ps1" @"
`$ErrorActionPreference = "Stop"
kubectl delete -k .\clusters\loudnova\apps\hello-web\overlays\home --ignore-not-found
"@

Write-File "terraform\platform\README.md" @"
# Terraform platform

Reserved for future Envoy Gateway, DNS, backup, and Hetzner disaster-recovery resources.
"@

Write-File "docs\architecture.md" @"
# Architecture

Windows PC -> Tailscale -> K3s API on LoudNova -> Traefik -> website services.
"@

Write-Host "Repository created successfully."
Write-Host "Run: Get-ChildItem -Recurse"
