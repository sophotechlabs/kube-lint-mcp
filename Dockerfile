# ---- Stage 1: Download CLI tools ----
FROM python:3.14-slim AS tools

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG TARGETARCH

ARG KUBECTL_VERSION=1.36.2
ARG HELM_VERSION=3.21.2
ARG FLUX_VERSION=2.8.8
ARG KUBECONFORM_VERSION=0.8.0
ARG ARGOCD_VERSION=3.4.4

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
FROM python:3.14-alpine@sha256:26730869004e2b9c4b9ad09cab8625e81d256d1ce97e72df5520e806b1709f92

LABEL io.modelcontextprotocol.server.name="io.github.sophotechlabs/kube-lint-mcp"

RUN addgroup -S nonroot && adduser -S -G nonroot -h /home/nonroot nonroot

COPY --from=tools /tools/kubectl /tools/helm /tools/flux /tools/kubeconform /tools/argocd /usr/local/bin/

COPY . /src
RUN pip install --no-cache-dir /src && rm -rf /src

USER nonroot

CMD ["python", "-m", "kube_lint_mcp"]
