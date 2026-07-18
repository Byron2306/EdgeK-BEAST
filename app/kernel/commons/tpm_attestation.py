"""Replay-safe TPM attestation contracts for Commons nodes.

This module deliberately separates evidence collection from appraisal.  A node
may submit a perfectly formed bundle and still remain ineligible: only results
produced by verifier-side cryptographic checks may satisfy an admission gate.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_PCRS = (0, 2, 4, 7, 10, 14)


@dataclass(frozen=True)
class TpmAttestationChallenge:
    challenge_id: str
    node_id: str
    nonce: str
    audience: str
    pcr_bank: str
    pcrs: tuple[int, ...]
    issued_at: float
    expires_at: float
    state: str = "issued"

    def public(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TpmVerificationResult:
    challenge_id: str
    node_id: str
    platform: str
    quote_valid: bool
    ek_public_matches_certificate: bool
    ek_chain_valid: bool
    ak_credential_activated: bool
    secure_boot_accepted: bool
    event_log_replay_valid: bool
    nonce_consumed: bool
    eligible_for_commons: bool
    reasons: tuple[str, ...]

    def mapping(self) -> dict[str, Any]:
        return asdict(self)


class TpmChallengeLedger:
    """Durable one-use challenge state with transactional consumption."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tpm_challenges (
                    challenge_id TEXT PRIMARY KEY,
                    node_id TEXT NOT NULL,
                    nonce TEXT NOT NULL UNIQUE,
                    audience TEXT NOT NULL,
                    pcr_bank TEXT NOT NULL,
                    pcrs_json TEXT NOT NULL,
                    issued_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    state TEXT NOT NULL,
                    consumed_at REAL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_tpm_challenge_node ON tpm_challenges(node_id, state)"
            )

    @staticmethod
    def _validate_pcrs(pcrs: tuple[int, ...]) -> tuple[int, ...]:
        normalized = tuple(sorted({int(value) for value in pcrs}))
        if not normalized or any(value < 0 or value > 23 for value in normalized):
            raise ValueError("PCR selection must contain TPM PCR indices 0 through 23")
        return normalized

    def issue(
        self,
        node_id: str,
        *,
        audience: str = "beast-commons-node-attestation",
        pcr_bank: str = "sha256",
        pcrs: tuple[int, ...] = DEFAULT_PCRS,
        ttl_seconds: float = 300.0,
        now: float | None = None,
    ) -> TpmAttestationChallenge:
        node = str(node_id).strip()
        target = str(audience).strip()
        bank = str(pcr_bank).strip().lower()
        if not node or not target:
            raise ValueError("node identity and audience are required")
        if bank != "sha256":
            raise ValueError("Commons TPM validation currently permits only SHA-256 PCRs")
        if ttl_seconds <= 0 or ttl_seconds > 900:
            raise ValueError("TPM challenge TTL must be between 0 and 900 seconds")
        selection = self._validate_pcrs(pcrs)
        moment = time.time() if now is None else float(now)
        challenge = TpmAttestationChallenge(
            challenge_id="tpm-challenge:" + secrets.token_hex(16),
            node_id=node,
            nonce=secrets.token_hex(32),
            audience=target,
            pcr_bank=bank,
            pcrs=selection,
            issued_at=moment,
            expires_at=moment + float(ttl_seconds),
        )
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE tpm_challenges
                   SET state = 'superseded'
                 WHERE node_id = ? AND audience = ? AND state = 'issued'
                """,
                (challenge.node_id, challenge.audience),
            )
            connection.execute(
                "INSERT INTO tpm_challenges VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    challenge.challenge_id,
                    challenge.node_id,
                    challenge.nonce,
                    challenge.audience,
                    challenge.pcr_bank,
                    json.dumps(challenge.pcrs),
                    challenge.issued_at,
                    challenge.expires_at,
                    challenge.state,
                ),
            )
        return challenge

    def snapshot(self, *, now: float | None = None) -> dict[str, int]:
        moment = time.time() if now is None else float(now)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE tpm_challenges
                   SET state = 'expired'
                 WHERE state = 'issued' AND expires_at <= ?
                """,
                (moment,),
            )
            rows = connection.execute(
                "SELECT state, COUNT(*) AS count FROM tpm_challenges GROUP BY state"
            ).fetchall()
        counts = {str(row["state"]): int(row["count"]) for row in rows}
        return {
            "issued": counts.get("issued", 0),
            "consumed": counts.get("consumed", 0),
            "expired": counts.get("expired", 0),
            "superseded": counts.get("superseded", 0),
        }

    @staticmethod
    def _from_row(row: sqlite3.Row) -> TpmAttestationChallenge:
        return TpmAttestationChallenge(
            challenge_id=str(row["challenge_id"]),
            node_id=str(row["node_id"]),
            nonce=str(row["nonce"]),
            audience=str(row["audience"]),
            pcr_bank=str(row["pcr_bank"]),
            pcrs=tuple(json.loads(row["pcrs_json"])),
            issued_at=float(row["issued_at"]),
            expires_at=float(row["expires_at"]),
            state=str(row["state"]),
        )

    def get(self, challenge_id: str) -> TpmAttestationChallenge:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM tpm_challenges WHERE challenge_id = ?", (challenge_id,)
            ).fetchone()
        if row is None:
            raise LookupError("unknown TPM attestation challenge")
        return self._from_row(row)

    def consume(
        self,
        challenge_id: str,
        *,
        node_id: str,
        nonce: str,
        now: float | None = None,
    ) -> TpmAttestationChallenge:
        """Atomically consume an already cryptographically verified challenge."""
        moment = time.time() if now is None else float(now)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM tpm_challenges WHERE challenge_id = ?", (challenge_id,)
            ).fetchone()
            if row is None:
                raise LookupError("unknown TPM attestation challenge")
            challenge = self._from_row(row)
            if challenge.state != "issued":
                raise PermissionError("TPM attestation challenge has already been consumed")
            if challenge.expires_at <= moment:
                connection.execute(
                    "UPDATE tpm_challenges SET state = 'expired' WHERE challenge_id = ?",
                    (challenge_id,),
                )
                connection.commit()
                raise PermissionError("TPM attestation challenge has expired")
            if challenge.node_id != str(node_id) or not secrets.compare_digest(
                challenge.nonce, str(nonce)
            ):
                raise PermissionError("TPM attestation challenge binding mismatch")
            updated = connection.execute(
                """
                UPDATE tpm_challenges
                   SET state = 'consumed', consumed_at = ?
                 WHERE challenge_id = ? AND state = 'issued'
                """,
                (moment, challenge_id),
            )
            if updated.rowcount != 1:
                raise PermissionError("TPM attestation challenge was consumed concurrently")
            connection.commit()
            return challenge
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()


def fail_closed_result(
    bundle: Mapping[str, Any],
    *,
    quote_valid: bool = False,
    ek_public_matches_certificate: bool = False,
    ek_chain_valid: bool = False,
    ak_credential_activated: bool = False,
    secure_boot_accepted: bool = False,
    event_log_replay_valid: bool = False,
    nonce_consumed: bool = False,
) -> TpmVerificationResult:
    """Derive admission only from verifier-produced facts, never node labels."""
    facts = {
        "quote_invalid": quote_valid,
        "ek_certificate_key_mismatch": ek_public_matches_certificate,
        "ek_chain_untrusted": ek_chain_valid,
        "ak_not_credential_activated": ak_credential_activated,
        "secure_boot_not_accepted": secure_boot_accepted,
        "event_log_not_replayed": event_log_replay_valid,
        "challenge_not_consumed": nonce_consumed,
    }
    reasons = tuple(name for name, passed in facts.items() if not passed)
    eligible = not reasons
    return TpmVerificationResult(
        challenge_id=str(bundle.get("challenge_id") or ""),
        node_id=str(bundle.get("node_id") or ""),
        platform=str(bundle.get("platform") or "unknown").lower(),
        quote_valid=quote_valid,
        ek_public_matches_certificate=ek_public_matches_certificate,
        ek_chain_valid=ek_chain_valid,
        ak_credential_activated=ak_credential_activated,
        secure_boot_accepted=secure_boot_accepted,
        event_log_replay_valid=event_log_replay_valid,
        nonce_consumed=nonce_consumed,
        eligible_for_commons=eligible,
        reasons=reasons,
    )
