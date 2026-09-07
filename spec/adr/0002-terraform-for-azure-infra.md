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

## Consequences
- Provisioning becomes reproducible and reviewable via pull request, at
  the cost of introducing a new toolchain (Terraform + the `azurerm`
  provider) that this repo's existing quality gates (`ci.yml`,
  pre-commit hooks) do not yet check — CI coverage for `/infra` (e.g.
  `terraform fmt`/`validate`) is a follow-up, not covered by this ADR.
- Terraform state must be stored somewhere outside this repository (e.g.
  an Azure Storage backend) before `apply` is run for real; this ADR
  covers the resource definitions only, not the state backend, which is
  an operational setup step for whoever runs `terraform apply`.
- Anyone applying this configuration needs Azure credentials with rights
  to create Cognitive Services resources in the target subscription —
  this is a manual, out-of-band step, not automated by this repo.
- Reversing this decision (e.g. moving to Bicep/ARM, or back to manual
  provisioning) means rewriting `/infra` and re-establishing however
  state and credentials are managed — a rewrite-scale change, hence an
  ADR rather than an implicit choice.
