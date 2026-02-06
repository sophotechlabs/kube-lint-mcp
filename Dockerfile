# ---- Stage 1: Build + install ----
FROM dhi.io/python:3.13-dev AS builder

ARG TARGETARCH

ARG KUBECTL_VERSION=1.32.1
ARG HELM_VERSION=3.17.1
ARG FLUX_VERSION=2.4.0
ARG KUBECONFORM_VERSION=0.6.7

RUN apt-get update && apt-get install -y --no-install-recommends curl gzip && rm -rf /var/lib/apt/lists/*

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

# Install Python package into a prefix we can copy
COPY . /src
RUN pip install --no-cache-dir --prefix=/install /src

# ---- Stage 2: Runtime ----
FROM dhi.io/python:3.13

COPY --from=builder /tools/kubectl /tools/helm /tools/flux /tools/kubeconform /usr/local/bin/
COPY --from=builder /install /home/nonroot/.local

CMD ["python", "-m", "kube_lint_mcp"]
