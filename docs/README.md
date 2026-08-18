# Documentation

This directory contains operational and engineering documentation for the MRA reference implementation.

## Start here

- [Architecture](architecture.md): components, data flow, trust boundaries, and package map.
- [Threat model](reference/threat-model.md): protected assets, actors, adversary knowledge, threats, and controls.
- [Adaptation profiles](reference/adaptation-profiles.md): whole-of-government baseline and adopter-specific configuration.
- [Production roadmap](reference/production-roadmap.md): work required to deploy the offline core as an accredited service.
- [Release process](releasing.md): versioning, validation, packaging, and GitHub release controls.

## Documentation policy

The repository does not contain papers, publication drafts, academic study reports, generated office documents, or presentation decks. Generated benchmark output belongs under `output/`, which is excluded from version control. Documentation should explain how to install, operate, integrate, secure, or contribute to the software.

Versioned machine contracts live in [`schemas/`](../schemas/), and executable examples live in [`examples/`](../examples/).
