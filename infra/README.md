# infra

Terraform configuration provisioning the Azure Cognitive Services Speech
resource that `transcribe` (see `../spec/spec.md`, ADR-0001, ADR-0002) calls
for transcription.

## Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.7.0
- An Azure subscription and credentials with rights to create resource
  groups and Cognitive Services accounts (e.g. via `az login`)

State is local (the default `terraform.tfstate` file, not a remote
backend) — see ADR-0002 for why. `terraform.tfstate*` is git-ignored;
never commit it, and keep it safe on whichever machine runs `apply`,
since it's the only record of what's been provisioned.

## Usage

```bash
cp terraform.tfvars.example terraform.tfvars   # then edit values
terraform init
terraform plan  -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

`terraform.tfvars` is git-ignored — never commit real resource names or
values beyond what's already in the example file.

## Outputs

| Output               | Feeds environment variable  |
|-----------------------|-----------------------------|
| `speech_endpoint`     | `AZURE_SPEECH_ENDPOINT`     |
| `speech_primary_key`  | `AZURE_SPEECH_KEY`          |

Read the sensitive key output with:

```bash
terraform output -raw speech_primary_key
```

Never print or log this value; pass it directly into your runtime's
secret store or environment.
