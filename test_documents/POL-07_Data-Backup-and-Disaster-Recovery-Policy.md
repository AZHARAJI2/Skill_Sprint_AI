POL-07 — Data Backup and Disaster Recovery Policy
v1 | 2026-03-20 | Engineering | Security

1. Scope
1.1 [M] This policy governs backup frequency, retention, and disaster-recovery procedures for all NovaCart production databases and file storage systems.
1.2 [M] "Recovery Point Objective (RPO)" under this policy means the maximum acceptable amount of data loss measured in time, currently set at 1 hour for production databases.

2. Backup Frequency and Retention
2.1 [M] Production databases must be backed up automatically every 6 hours, with backups retained for 30 days.
2.2 [O] Teams are encouraged to perform a manual backup-restore verification test monthly, in addition to the automated schedule.

3. Conditional Requirements
3.1 [M] CONDITIONAL: If a system stores customer payment data, backups of that system must be encrypted at rest using a key managed by the Security team, per POL-06 Section 1.2.

4. Disaster Recovery Testing
4.1 [M] A full disaster-recovery failover test must be conducted at least once per year, with results reported to the CISO.

5. Appendix
5.1 This document outlines baseline backup and recovery standards for system auditing and compliance verification.
