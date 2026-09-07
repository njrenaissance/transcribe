# ADR-0002: Provision Azure infrastructure with Terraform under /infra

## Status
accepted

## Context
ADR-0001 commits `transcribe` to Azure AI Speech, which requires a
provisioned Azure Cognitive Services (Speech) resource before the CLI can
run against it. This project currently has no infrastructure-as-code of
any kind — it's a plain `uv`-managed Python package. Provisioning the
Speech resource by hand (Azure Portal or ad hoc CLI commands) would leave
its configuration undocumented and unreproducible, and would not fit this
repo's existing standard of checked-in, versioned change history
(`.claude/standards/database.md` establishes the same principle for schema
changes via migrations).

## Decision
Define the required Azure resources (resource group and
`azurerm_cognitive_account` of kind `SpeechServices`) as Terraform
configuration under `/infra`, using the `azurerm` provider with pinned
version constraints. Resource naming, location, and SKU are exposed as
input variables rather than hardcoded; the Speech endpoint and key are
exposed as outputs, with the key marked `sensitive`. No `.tfvars` file
with real values, and no Terraform state, is committed to the repository.

State is kept **local** (Terraform's default `terraform.tfstate` on the
machine that runs `apply`) rather than a remote backend (e.g. an Azure
Storage backend). This project has a single, small piece of
infrastructure and no team-collaboration requirement yet — a remote
backend adds its own resources, access control, and setup to provision
before provisioning anything else, which is disproportionate at this
scale. Revisit this once more than one person or environment needs to run
`apply` against the same state.

## Consequences
- Provisioning becomes reproducible and reviewable via pull request, at
  the cost of introducing a new toolchain (Terraform + the `azurerm`
  provider) that this repo's existing quality gates (`ci.yml`,
  pre-commit hooks) do not yet check — CI coverage for `/infra` (e.g.
  `terraform fmt`/`validate`) is a follow-up, not covered by this ADR.
- Local state means only the machine holding `terraform.tfstate` can
  safely run `terraform apply`/`destroy` again; there's no locking or
  shared source of truth, so two people (or CI and a person) applying
  concurrently, or the state file being lost, can desync the state from
  the real Azure resources. Acceptable now because at most one operator
  is expected to manage this infrastructure; revisit (move to a remote
  backend) the moment that stops being true.
- Anyone applying this configuration needs Azure credentials with rights
  to create Cognitive Services resources in the target subscription —
  this is a manual, out-of-band step, not automated by this repo.
- Reversing this decision (e.g. moving to Bicep/ARM, or back to manual
  provisioning) means rewriting `/infra` and re-establishing however
  state and credentials are managed — a rewrite-scale change, hence an
  ADR rather than an implicit choice. Moving from local to remote state
  later is comparatively cheap (`terraform init -migrate-state`), and
  isn't itself a reason to avoid starting local.
