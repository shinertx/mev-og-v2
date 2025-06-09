"""
Voting and Quorum System for AI Mutations.
Ensures multi-signature approval before strategy mutations go live.
"""

import json
import hashlib
import hmac
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, asdict
from enum import Enum
import asyncio

from core.logger import StructuredLogger

LOG = StructuredLogger("voting", log_file="logs/voting.json")
VOTE_DIR = Path("telemetry/ai_votes")
VOTE_DIR.mkdir(parents=True, exist_ok=True)


class VoteType(Enum):
    APPROVE = "approve"
    REJECT = "reject"
    ABSTAIN = "abstain"


class ProposalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    EXECUTED = "executed"


@dataclass
class Vote:
    voter_id: str
    vote_type: VoteType
    timestamp: str
    signature: str
    reason: Optional[str] = None
    risk_assessment: Optional[Dict] = None


@dataclass
class MutationProposal:
    proposal_id: str
    strategy_id: str
    mutation_type: str
    mutation_data: Dict
    proposer: str
    created_at: str
    expires_at: str
    status: ProposalStatus
    votes: List[Vote]
    quorum_required: int
    approval_threshold: float
    risk_level: str
    audit_results: Optional[Dict] = None
    execution_tx: Optional[str] = None


class VotingQuorum:
    """Multi-signature voting for mutation approval."""
    
    def __init__(
        self,
        quorum_threshold: int = 3,
        approval_percentage: float = 0.66,
        vote_timeout_hours: int = 24,
        authorized_voters: Optional[List[str]] = None
    ):
        self.quorum_threshold = quorum_threshold
        self.approval_percentage = approval_percentage
        self.vote_timeout_hours = vote_timeout_hours
        self.vote_storage = VOTE_DIR
        
        # Load authorized voters from env or use defaults
        if authorized_voters:
            self.authorized_voters = set(authorized_voters)
        else:
            self.authorized_voters = self._load_authorized_voters()
        
        # Ensure we have enough voters for quorum
        if len(self.authorized_voters) < self.quorum_threshold:
            raise ValueError(f"Need at least {self.quorum_threshold} authorized voters")
        
        self.proposals_file = self.vote_storage / "proposals.json"
        self.proposals = self._load_proposals()
    
    def _load_authorized_voters(self) -> Set[str]:
        """Load authorized voter IDs from configuration."""
        voters = set()
        
        # From environment variables
        for i in range(1, 10):
            voter = os.getenv(f"AUTHORIZED_VOTER_{i}")
            if voter:
                voters.add(voter)
        
        # From config file
        config_file = Path("config/authorized_voters.json")
        if config_file.exists():
            with open(config_file) as f:
                config_voters = json.load(f)
                voters.update(config_voters)
        
        # Default test voters if none configured
        if not voters:
            voters = {"voter1", "voter2", "voter3", "founder", "auditor"}
        
        return voters
    
    def _load_proposals(self) -> Dict[str, MutationProposal]:
        """Load existing proposals from storage."""
        if self.proposals_file.exists():
            with open(self.proposals_file) as f:
                data = json.load(f)
                proposals = {}
                for pid, pdata in data.items():
                    # Convert to dataclass
                    votes = [Vote(**v) for v in pdata.pop("votes", [])]
                    pdata["votes"] = votes
                    pdata["status"] = ProposalStatus(pdata["status"])
                    proposals[pid] = MutationProposal(**pdata)
                return proposals
        return {}
    
    def _save_proposals(self):
        """Save proposals to storage."""
        data = {}
        for pid, proposal in self.proposals.items():
            pdict = asdict(proposal)
            # Convert enums to strings
            pdict["status"] = proposal.status.value
            pdict["votes"] = [
                {**asdict(v), "vote_type": v.vote_type.value}
                for v in proposal.votes
            ]
            data[pid] = pdict
        
        with open(self.proposals_file, "w") as f:
            json.dump(data, f, indent=2)
    
    def _generate_signature(self, voter_id: str, proposal_id: str, vote_type: str) -> str:
        """Generate HMAC signature for vote integrity."""
        secret = os.getenv(f"VOTER_SECRET_{voter_id}", "default_secret")
        message = f"{voter_id}:{proposal_id}:{vote_type}:{time.time()}"
        
        signature = hmac.new(
            secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    def _verify_signature(self, vote: Vote, proposal_id: str) -> bool:
        """Verify vote signature."""
        # In production, implement proper signature verification
        # For now, check that signature exists and is valid format
        return bool(vote.signature) and len(vote.signature) == 64
    
    def create_mutation_proposal(
        self,
        strategy_id: str,
        mutation_type: str,
        mutation_data: Dict,
        proposer: str,
        risk_level: str = "medium",
        audit_results: Optional[Dict] = None
    ) -> str:
        """Create a new mutation proposal requiring votes."""
        if proposer not in self.authorized_voters:
            raise ValueError(f"Proposer {proposer} not authorized")
        
        # Generate proposal ID
        proposal_content = f"{strategy_id}:{mutation_type}:{json.dumps(mutation_data, sort_keys=True)}"
        proposal_id = hashlib.sha256(proposal_content.encode()).hexdigest()[:16]
        
        # Check if already exists
        if proposal_id in self.proposals:
            return proposal_id
        
        # Create proposal
        now = datetime.now(timezone.utc)
        proposal = MutationProposal(
            proposal_id=proposal_id,
            strategy_id=strategy_id,
            mutation_type=mutation_type,
            mutation_data=mutation_data,
            proposer=proposer,
            created_at=now.isoformat(),
            expires_at=(now + timedelta(hours=self.vote_timeout_hours)).isoformat(),
            status=ProposalStatus.PENDING,
            votes=[],
            quorum_required=self.quorum_threshold,
            approval_threshold=self.approval_percentage,
            risk_level=risk_level,
            audit_results=audit_results,
            execution_tx=None
        )
        
        self.proposals[proposal_id] = proposal
        self._save_proposals()
        
        # Log creation
        LOG.log(
            "proposal_created",
            proposal_id=proposal_id,
            strategy_id=strategy_id,
            mutation_type=mutation_type,
            proposer=proposer,
            risk_level=risk_level
        )
        
        # Notify voters
        self._notify_voters(proposal)
        
        return proposal_id
    
    def cast_vote(
        self,
        proposal_id: str,
        voter_id: str,
        vote_type: VoteType,
        reason: Optional[str] = None,
        risk_assessment: Optional[Dict] = None
    ) -> bool:
        """Cast a vote on a proposal."""
        if voter_id not in self.authorized_voters:
            raise ValueError(f"Voter {voter_id} not authorized")
        
        if proposal_id not in self.proposals:
            raise ValueError(f"Proposal {proposal_id} not found")
        
        proposal = self.proposals[proposal_id]
        
        # Check if expired
        if datetime.now(timezone.utc) > datetime.fromisoformat(proposal.expires_at):
            proposal.status = ProposalStatus.EXPIRED
            self._save_proposals()
            return False
        
        # Check if already voted
        if any(v.voter_id == voter_id for v in proposal.votes):
            raise ValueError(f"Voter {voter_id} already voted")
        
        # Create vote
        signature = self._generate_signature(voter_id, proposal_id, vote_type.value)
        vote = Vote(
            voter_id=voter_id,
            vote_type=vote_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            signature=signature,
            reason=reason,
            risk_assessment=risk_assessment
        )
        
        # Verify signature
        if not self._verify_signature(vote, proposal_id):
            raise ValueError("Invalid vote signature")
        
        # Add vote
        proposal.votes.append(vote)
        
        # Check if quorum reached
        self._check_quorum(proposal)
        
        self._save_proposals()
        
        # Log vote
        LOG.log(
            "vote_cast",
            proposal_id=proposal_id,
            voter_id=voter_id,
            vote_type=vote_type.value,
            reason=reason,
            current_votes=len(proposal.votes),
            quorum_required=proposal.quorum_required
        )
        
        return True
    
    def _check_quorum(self, proposal: MutationProposal):
        """Check if proposal has reached quorum and update status."""
        if proposal.status != ProposalStatus.PENDING:
            return
        
        total_votes = len(proposal.votes)
        
        if total_votes >= proposal.quorum_required:
            # Count approvals
            approvals = sum(1 for v in proposal.votes if v.vote_type == VoteType.APPROVE)
            approval_rate = approvals / total_votes
            
            if approval_rate >= proposal.approval_threshold:
                proposal.status = ProposalStatus.APPROVED
                LOG.log(
                    "proposal_approved",
                    proposal_id=proposal.proposal_id,
                    approvals=approvals,
                    total_votes=total_votes,
                    approval_rate=approval_rate
                )
                
                # Trigger execution
                self._schedule_execution(proposal)
            else:
                proposal.status = ProposalStatus.REJECTED
                LOG.log(
                    "proposal_rejected",
                    proposal_id=proposal.proposal_id,
                    approvals=approvals,
                    total_votes=total_votes,
                    approval_rate=approval_rate
                )
    
    def _schedule_execution(self, proposal: MutationProposal):
        """Schedule approved proposal for execution."""
        execution_queue = Path("ai/execution_queue")
        execution_queue.mkdir(parents=True, exist_ok=True)
        
        execution_file = execution_queue / f"{proposal.proposal_id}.json"
        with open(execution_file, "w") as f:
            json.dump({
                "proposal_id": proposal.proposal_id,
                "strategy_id": proposal.strategy_id,
                "mutation_type": proposal.mutation_type,
                "mutation_data": proposal.mutation_data,
                "approved_at": datetime.now(timezone.utc).isoformat(),
                "risk_level": proposal.risk_level,
                "votes": [
                    {
                        "voter": v.voter_id,
                        "vote": v.vote_type.value,
                        "reason": v.reason
                    }
                    for v in proposal.votes
                ]
            }, f, indent=2)
        
        LOG.log(
            "execution_scheduled",
            proposal_id=proposal.proposal_id,
            execution_file=str(execution_file)
        )
    
    def _notify_voters(self, proposal: MutationProposal):
        """Notify authorized voters of new proposal."""
        # In production, send notifications via Discord/Telegram/Email
        notification = {
            "type": "new_proposal",
            "proposal_id": proposal.proposal_id,
            "strategy_id": proposal.strategy_id,
            "mutation_type": proposal.mutation_type,
            "risk_level": proposal.risk_level,
            "expires_at": proposal.expires_at,
            "vote_url": f"https://mev-og.app/vote/{proposal.proposal_id}"
        }
        
        notification_file = self.vote_storage / "pending_notifications" / f"{proposal.proposal_id}.json"
        notification_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(notification_file, "w") as f:
            json.dump(notification, f, indent=2)
    
    def get_proposal_status(self, proposal_id: str) -> Dict:
        """Get current status of a proposal."""
        if proposal_id not in self.proposals:
            return {"error": "Proposal not found"}
        
        proposal = self.proposals[proposal_id]
        
        # Check expiry
        if (proposal.status == ProposalStatus.PENDING and 
            datetime.now(timezone.utc) > datetime.fromisoformat(proposal.expires_at)):
            proposal.status = ProposalStatus.EXPIRED
            self._save_proposals()
        
        return {
            "proposal_id": proposal_id,
            "status": proposal.status.value,
            "votes_received": len(proposal.votes),
            "quorum_required": proposal.quorum_required,
            "approval_threshold": proposal.approval_threshold,
            "expires_at": proposal.expires_at,
            "votes": [
                {
                    "voter": v.voter_id,
                    "vote": v.vote_type.value,
                    "timestamp": v.timestamp,
                    "reason": v.reason
                }
                for v in proposal.votes
            ],
            "can_execute": proposal.status == ProposalStatus.APPROVED
        }
    
    def execute_approved_proposal(self, proposal_id: str, executor_id: str) -> bool:
        """Execute an approved proposal."""
        if executor_id not in self.authorized_voters:
            raise ValueError(f"Executor {executor_id} not authorized")
        
        if proposal_id not in self.proposals:
            return False
        
        proposal = self.proposals[proposal_id]
        
        if proposal.status != ProposalStatus.APPROVED:
            return False
        
        # Mark as executed
        proposal.status = ProposalStatus.EXECUTED
        proposal.execution_tx = f"exec_{proposal_id}_{int(time.time())}"
        self._save_proposals()
        
        # Log execution
        LOG.log(
            "proposal_executed",
            proposal_id=proposal_id,
            executor_id=executor_id,
            execution_tx=proposal.execution_tx
        )
        
        return True
    
    def quorum_met(self, proposal_id: str) -> bool:
        """Check if quorum has been met for a proposal."""
        if proposal_id not in self.proposals:
            return False
        
        proposal = self.proposals[proposal_id]
        return proposal.status in [ProposalStatus.APPROVED, ProposalStatus.EXECUTED]
    
    def get_pending_proposals(self) -> List[Dict]:
        """Get all pending proposals requiring votes."""
        pending = []
        
        for proposal in self.proposals.values():
            if proposal.status == ProposalStatus.PENDING:
                # Check expiry
                if datetime.now(timezone.utc) > datetime.fromisoformat(proposal.expires_at):
                    proposal.status = ProposalStatus.EXPIRED
                else:
                    pending.append({
                        "proposal_id": proposal.proposal_id,
                        "strategy_id": proposal.strategy_id,
                        "mutation_type": proposal.mutation_type,
                        "risk_level": proposal.risk_level,
                        "votes_needed": proposal.quorum_required - len(proposal.votes),
                        "expires_in_hours": (
                            datetime.fromisoformat(proposal.expires_at) - 
                            datetime.now(timezone.utc)
                        ).total_seconds() / 3600
                    })
        
        self._save_proposals()
        return pending
    
    def cleanup_expired_proposals(self, days_to_keep: int = 30):
        """Clean up old expired/rejected proposals."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
        
        to_remove = []
        for pid, proposal in self.proposals.items():
            if proposal.status in [ProposalStatus.EXPIRED, ProposalStatus.REJECTED]:
                created = datetime.fromisoformat(proposal.created_at)
                if created < cutoff:
                    to_remove.append(pid)
        
        for pid in to_remove:
            # Archive before removing
            archive_dir = self.vote_storage / "archive" / pid[:4]
            archive_dir.mkdir(parents=True, exist_ok=True)
            
            with open(archive_dir / f"{pid}.json", "w") as f:
                json.dump(asdict(self.proposals[pid]), f, indent=2)
            
            del self.proposals[pid]
        
        self._save_proposals()
        
        if to_remove:
            LOG.log(
                "proposals_cleaned",
                removed_count=len(to_remove),
                removed_ids=to_remove
            )


# Integration with mutation system
def integrate_voting_with_mutations():
    """Integration code for existing mutation system."""
    
    voting = VotingQuorum()
    
    # Check for any mutation requests
    mutation_queue = Path("ai/mutation_requests")
    if not mutation_queue.exists():
        return
    
    for request_file in mutation_queue.glob("*.json"):
        with open(request_file) as f:
            request = json.load(f)
        
        # Create proposal
        proposal_id = voting.create_mutation_proposal(
            strategy_id=request.get("strategy_id", "unknown"),
            mutation_type=request.get("mutation_type", "parameter_update"),
            mutation_data=request.get("mutation_data", {}),
            proposer=request.get("proposer", "ai_system"),
            risk_level=request.get("risk_level", "medium"),
            audit_results=request.get("audit_results")
        )
        
        # Move to pending
        pending_dir = mutation_queue / "pending"
        pending_dir.mkdir(exist_ok=True)
        request_file.rename(pending_dir / f"{proposal_id}.json")
    
    return voting


# CLI interface for voting
async def cli_vote_interface():
    """Interactive CLI for voting on proposals."""
    voting = VotingQuorum()
    
    print("=== MEV-OG Voting System ===")
    print(f"Authorized voters: {voting.authorized_voters}")
    
    # Get pending proposals
    pending = voting.get_pending_proposals()
    
    if not pending:
        print("No pending proposals.")
        return
    
    print(f"\nPending proposals: {len(pending)}")
    for i, prop in enumerate(pending):
        print(f"\n{i+1}. Proposal {prop['proposal_id']}")
        print(f"   Strategy: {prop['strategy_id']}")
        print(f"   Type: {prop['mutation_type']}")
        print(f"   Risk: {prop['risk_level']}")
        print(f"   Votes needed: {prop['votes_needed']}")
        print(f"   Expires in: {prop['expires_in_hours']:.1f} hours")
    
    # Get voter ID
    voter_id = input("\nEnter your voter ID: ").strip()
    if voter_id not in voting.authorized_voters:
        print("Error: Not an authorized voter")
        return
    
    # Select proposal
    try:
        choice = int(input("Select proposal number (0 to exit): "))
        if choice == 0:
            return
        
        proposal = pending[choice - 1]
        proposal_id = proposal["proposal_id"]
        
        # Get full proposal details
        details = voting.get_proposal_status(proposal_id)
        print(f"\nProposal details: {json.dumps(details, indent=2)}")
        
        # Cast vote
        vote_input = input("\nVote (a)pprove, (r)eject, (s)kip: ").lower()
        
        if vote_input == "a":
            vote_type = VoteType.APPROVE
        elif vote_input == "r":
            vote_type = VoteType.REJECT
        elif vote_input == "s":
            vote_type = VoteType.ABSTAIN
        else:
            print("Invalid vote")
            return
        
        reason = input("Reason (optional): ").strip() or None
        
        # Cast the vote
        success = voting.cast_vote(
            proposal_id=proposal_id,
            voter_id=voter_id,
            vote_type=vote_type,
            reason=reason
        )
        
        if success:
            print("Vote cast successfully!")
            
            # Check new status
            new_status = voting.get_proposal_status(proposal_id)
            print(f"Proposal status: {new_status['status']}")
            
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    # Run CLI interface
    asyncio.run(cli_vote_interface())
