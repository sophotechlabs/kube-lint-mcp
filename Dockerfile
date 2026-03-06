# ---- Stage 1: Download CLI tools ----
FROM python:3.14-slim AS tools

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG TARGETARCH

ARG KUBECTL_VERSION=1.35.2
ARG HELM_VERSION=3.20.0
ARG FLUX_VERSION=2.8.1
ARG KUBECONFORM_VERSION=0.7.0
ARG ARGOCD_VERSION=3.3.2

# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /tools

# kubectl
RUN curl -fsSL "https://dl.k8s.io/release/v${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl" -o kubectl \
    && chmod +x kubectl

# helm
RUN curl -fsSL "https://get.helm.sh/helm-v${HELM_VERSION}-linux-${TARGETARCH}.tar.gz" \
    | tar xz --strip-components=1 -C . "linux-${TARGETARCH}/helm"

# flux
RUN curl -fsSL "https://github.com/fluxcd/flux2/releases/download/v${FLUX_VERSION}/flux_${FLUX_VERSION}_linux_${TARGETARCH}.tar.gz" \
    | tar xz -C . flux

# kubeconform
RUN curl -fsSL "https://github.com/yannh/kubeconform/releases/download/v${KUBECONFORM_VERSION}/kubeconform-linux-${TARGETARCH}.tar.gz" \
    | tar xz -C . kubeconform

# argocd
RUN curl -fsSL "https://github.com/argoproj/argo-cd/releases/download/v${ARGOCD_VERSION}/argocd-linux-${TARGETARCH}" -o argocd \
    && chmod +x argocd

# ---- Stage 2: Runtime ----
FROM python:3.14-alpine@sha256:faee120f7885a06fcc9677922331391fa690d911c020abb9e8025ff3d908e510

RUN addgroup -S nonroot && adduser -S -G nonroot -h /home/nonroot nonroot

COPY --from=tools /tools/kubectl /tools/helm /tools/flux /tools/kubeconform /tools/argocd /usr/local/bin/

COPY . /src
RUN pip install --no-cache-dir /src && rm -rf /src

USER nonroot

CMD ["python", "-m", "kube_lint_mcp"]
