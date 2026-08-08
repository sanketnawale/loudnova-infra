$ErrorActionPreference = "Stop"

$expectedContext = "loudnova-home"
$currentContext = kubectl config current-context

if ($currentContext -ne $expectedContext) {
    throw "Wrong Kubernetes context: '$currentContext'. Expected '$expectedContext'."
}

Write-Host "Applying hello-web..."
kubectl apply -k .\clusters\loudnova\apps\hello-web\overlays\home

Write-Host "Waiting for rollout..."
kubectl rollout status deployment/hello-web `
    --namespace hello-web `
    --timeout=180s

Write-Host "Deployment completed."
kubectl get pods,svc,ingress -n hello-web