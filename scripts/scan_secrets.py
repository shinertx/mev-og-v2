#!/usr/bin/env python3
"""
Automated Secret Scanner for MEV-OG.
Scans codebase, logs, and exports for exposed secrets.
Integrates with CI/CD and provides real-time monitoring.
"""

import os
import re
import json
import sys
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Set, Tuple, Optional
import argparse
from dataclasses import dataclass, asdict
from enum import Enum

# Try to import optional dependencies
try:
    import git
    HAS_GIT = True
except ImportError:
    HAS_GIT = False

try:
    import yara
    HAS_YARA = True
except ImportError:
    HAS_YARA = False


class SecretType(Enum):
    API_KEY = "api_key"
    PRIVATE_KEY = "private_key"
    WEBHOOK_URL = "webhook_url"
    DATABASE_URL = "database_url"
    AWS_CREDENTIAL = "aws_credential"
    JWT_TOKEN = "jwt_token"
    OAUTH_TOKEN = "oauth_token"
    GENERIC_SECRET = "generic_secret"


@dataclass
class SecretFinding:
    file_path: str
    line_number: int
    secret_type: SecretType
    matched_pattern: str
    context: str
    severity: str
    confidence: float
    hash: str


class SecretScanner:
    """Comprehensive secret scanner with multiple detection methods."""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config = self._load_config(config_path)
        self.patterns = self._build_patterns()
        self.whitelist = self._load_whitelist()
        self.findings: List[SecretFinding] = []
        self.scanned_files = 0
        self.scan_start_time = None
        
        # YARA rules if available
        if HAS_YARA:
            self.yara_rules = self._compile_yara_rules()
        else:
            self.yara_rules = None
    
    def _load_config(self, config_path: Optional[str]) -> Dict:
        """Load scanner configuration."""
        default_config = {
            "scan_extensions": [".py", ".js", ".json", ".yaml", ".yml", ".env", ".sh", ".md", ".txt"],
            "exclude_dirs": ["venv", ".git", "__pycache__", "node_modules", ".pytest_cache"],
            "exclude_files": ["scan_secrets.py", "secret_scanner.py"],
            "min_entropy": 3.5,
            "max_file_size_mb": 10
        }
        
        if config_path and Path(config_path).exists():
            with open(config_path) as f:
                user_config = json.load(f)
                default_config.update(user_config)
        
        return default_config
    
    def _build_patterns(self) -> Dict[SecretType, List[re.Pattern]]:
        """Build regex patterns for secret detection."""
        patterns = {
            SecretType.API_KEY: [
                re.compile(r'["\']?api[_-]?key["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?', re.I),
                re.compile(r'["\']?apikey["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?', re.I),
                re.compile(r'["\']?api[_-]?secret["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?', re.I),
                re.compile(r'X-API-KEY["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?', re.I),
            ],
            SecretType.PRIVATE_KEY: [
                re.compile(r'["\']?private[_-]?key["\']?\s*[:=]\s*["\']?(0x[a-fA-F0-9]{64})["\']?', re.I),
                re.compile(r'["\']?priv[_-]?key["\']?\s*[:=]\s*["\']?(0x[a-fA-F0-9]{64})["\']?', re.I),
                re.compile(r'-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----'),
                re.compile(r'["\']?secret[_-]?key["\']?\s*[:=]\s*["\']?([a-fA-F0-9]{64})["\']?', re.I),
            ],
            SecretType.WEBHOOK_URL: [
                re.compile(r'webhook[_-]?url["\']?\s*[:=]\s*["\']?(https?://[^\s"\']+)["\']?', re.I),
                re.compile(r'discord[_-]?webhook["\']?\s*[:=]\s*["\']?(https?://[^\s"\']+)["\']?', re.I),
                re.compile(r'slack[_-]?webhook["\']?\s*[:=]\s*["\']?(https?://[^\s"\']+)["\']?', re.I),
            ],
            SecretType.DATABASE_URL: [
                re.compile(r'(postgres|postgresql|mysql|mongodb|redis)://[^\s"\']+:[^\s"\']+@[^\s"\']+', re.I),
                re.compile(r'database[_-]?url["\']?\s*[:=]\s*["\']?([^\s"\']+)["\']?', re.I),
            ],
            SecretType.AWS_CREDENTIAL: [
                re.compile(r'aws[_-]?access[_-]?key[_-]?id["\']?\s*[:=]\s*["\']?([A-Z0-9]{20})["\']?', re.I),
                re.compile(r'aws[_-]?secret[_-]?access[_-]?key["\']?\s*[:=]\s*["\']?([a-zA-Z0-9/+=]{40})["\']?', re.I),
                re.compile(r'AKIA[A-Z0-9]{16}'),  # AWS Access Key ID format
            ],
            SecretType.JWT_TOKEN: [
                re.compile(r'["\']?jwt[_-]?token["\']?\s*[:=]\s*["\']?(eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+)["\']?', re.I),
                re.compile(r'["\']?bearer["\']?\s*[:=]\s*["\']?(eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+)["\']?', re.I),
            ],
            SecretType.OAUTH_TOKEN: [
                re.compile(r'["\']?oauth[_-]?token["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?', re.I),
                re.compile(r'["\']?access[_-]?token["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?', re.I),
                re.compile(r'["\']?refresh[_-]?token["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?', re.I),
            ],
            SecretType.GENERIC_SECRET: [
                re.compile(r'["\']?password["\']?\s*[:=]\s*["\']?([^\s"\']{8,})["\']?', re.I),
                re.compile(r'["\']?passwd["\']?\s*[:=]\s*["\']?([^\s"\']{8,})["\']?', re.I),
                re.compile(r'["\']?secret["\']?\s*[:=]\s*["\']?([^\s"\']{16,})["\']?', re.I),
                re.compile(r'["\']?token["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?', re.I),
            ]
        }
        
        return patterns
    
    def _load_whitelist(self) -> Set[str]:
        """Load whitelisted patterns that should be ignored."""
        whitelist_file = Path("config/secret_whitelist.json")
        whitelist = {
            "0x0000000000000000000000000000000000000000",  # Null address
            "0x" + "0" * 64,  # Zero private key
            "example.com",
            "localhost",
            "127.0.0.1",
            "YOUR_API_KEY_HERE",
            "YOUR_PRIVATE_KEY_HERE",
            "<your-api-key>",
            "<your-private-key>",
            "xxx",
            "XXX",
        }
        
        if whitelist_file.exists():
            with open(whitelist_file) as f:
                whitelist.update(json.load(f))
        
        return whitelist
    
    def _compile_yara_rules(self) -> Optional[yara.Rules]:
        """Compile YARA rules for advanced detection."""
        if not HAS_YARA:
            return None
        
        rules_content = '''
        rule PrivateKey {
            strings:
                $hex_key = /0x[a-fA-F0-9]{64}/
                $pem_header = "-----BEGIN PRIVATE KEY-----"
                $rsa_header = "-----BEGIN RSA PRIVATE KEY-----"
            condition:
                any of them
        }
        
        rule APIKey {
            strings:
                $api1 = /api[_-]?key\s*[:=]\s*["']?[a-zA-Z0-9_\-]{20,}["']?/i
                $api2 = /X-API-KEY\s*[:=]\s*["']?[a-zA-Z0-9_\-]{20,}["']?/i
                $bearer = /Bearer\s+[a-zA-Z0-9_\-]{20,}/
            condition:
                any of them
        }
        
        rule AWSCredentials {
            strings:
                $aws_key = /AKIA[A-Z0-9]{16}/
                $aws_secret = /aws_secret_access_key\s*[:=]\s*["']?[a-zA-Z0-9\/+=]{40}["']?/i
            condition:
                any of them
        }
        '''
        
        try:
            return yara.compile(source=rules_content)
        except Exception as e:
            print(f"Failed to compile YARA rules: {e}")
            return None
    
    def _calculate_entropy(self, data: str) -> float:
        """Calculate Shannon entropy of a string."""
        if not data:
            return 0.0
        
        entropy = 0.0
        for i in range(256):
            pi = data.count(chr(i)) / len(data)
            if pi > 0:
                entropy -= pi * (pi and sum(pi * -1 * (pi and log2(pi) or 0) for pi in [pi]))
        
        return entropy
    
    def scan_file(self, file_path: Path) -> List[SecretFinding]:
        """Scan a single file for secrets."""
        findings = []
        
        # Check file size
        if file_path.stat().st_size > self.config["max_file_size_mb"] * 1024 * 1024:
            return findings
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                lines = content.splitlines()
            
            # Regex pattern matching
            for secret_type, patterns in self.patterns.items():
                for pattern in patterns:
                    for line_num, line in enumerate(lines, 1):
                        matches = pattern.finditer(line)
                        for match in matches:
                            secret_value = match.group(1) if match.groups() else match.group(0)
                            
                            # Skip whitelisted values
                            if secret_value in self.whitelist:
                                continue
                            
                            # Skip low entropy secrets for generic types
                            if secret_type == SecretType.GENERIC_SECRET:
                                entropy = self._calculate_entropy(secret_value)
                                if entropy < self.config["min_entropy"]:
                                    continue
                            
                            # Create finding
                            finding = SecretFinding(
                                file_path=str(file_path),
                                line_number=line_num,
                                secret_type=secret_type,
                                matched_pattern=pattern.pattern,
                                context=line.strip(),
                                severity=self._get_severity(secret_type),
                                confidence=self._get_confidence(secret_type, secret_value),
                                hash=hashlib.sha256(secret_value.encode()).hexdigest()[:16]
                            )
                            
                            findings.append(finding)
            
            # YARA scanning
            if self.yara_rules and HAS_YARA:
                yara_matches = self.yara_rules.match(data=content)
                for match in yara_matches:
                    for string_match in match.strings:
                        line_num = content[:string_match[0]].count('\n') + 1
                        finding = SecretFinding(
                            file_path=str(file_path),
                            line_number=line_num,
                            secret_type=self._yara_rule_to_type(match.rule),
                            matched_pattern=f"YARA:{match.rule}",
                            context=lines[line_num - 1].strip() if line_num <= len(lines) else "",
                            severity="high",
                            confidence=0.9,
                            hash=hashlib.sha256(string_match[2].encode()).hexdigest()[:16]
                        )
                        findings.append(finding)
        
        except Exception as e:
            print(f"Error scanning {file_path}: {e}")
        
        return findings
    
    def _get_severity(self, secret_type: SecretType) -> str:
        """Determine severity based on secret type."""
        high_severity = {
            SecretType.PRIVATE_KEY,
            SecretType.AWS_CREDENTIAL,
            SecretType.DATABASE_URL
        }
        
        medium_severity = {
            SecretType.API_KEY,
            SecretType.JWT_TOKEN,
            SecretType.OAUTH_TOKEN
        }
        
        if secret_type in high_severity:
            return "high"
        elif secret_type in medium_severity:
            return "medium"
        else:
            return "low"
    
    def _get_confidence(self, secret_type: SecretType, value: str) -> float:
        """Calculate confidence score for a finding."""
        confidence = 0.5
        
        # Length-based confidence
        if len(value) > 40:
            confidence += 0.2
        elif len(value) > 20:
            confidence += 0.1
        
        # Pattern-specific confidence
        if secret_type == SecretType.PRIVATE_KEY and value.startswith("0x"):
            confidence += 0.3
        elif secret_type == SecretType.AWS_CREDENTIAL and value.startswith("AKIA"):
            confidence += 0.4
        
        # Entropy-based confidence for generic secrets
        if secret_type == SecretType.GENERIC_SECRET:
            entropy = self._calculate_entropy(value)
            if entropy > 4.5:
                confidence += 0.3
            elif entropy > 4.0:
                confidence += 0.2
        
        return min(confidence, 1.0)
    
    def _yara_rule_to_type(self, rule_name: str) -> SecretType:
        """Map YARA rule name to secret type."""
        mapping = {
            "PrivateKey": SecretType.PRIVATE_KEY,
            "APIKey": SecretType.API_KEY,
            "AWSCredentials": SecretType.AWS_CREDENTIAL
        }
        return mapping.get(rule_name, SecretType.GENERIC_SECRET)
    
    def scan_directory(self, directory: Path) -> List[SecretFinding]:
        """Recursively scan a directory for secrets."""
        self.scan_start_time = datetime.now(timezone.utc)
        findings = []
        
        for file_path in directory.rglob("*"):
            # Skip excluded directories
            if any(excluded in file_path.parts for excluded in self.config["exclude_dirs"]):
                continue
            
            # Skip excluded files
            if file_path.name in self.config["exclude_files"]:
                continue
            
            # Check file extension
            if file_path.is_file() and file_path.suffix in self.config["scan_extensions"]:
                self.scanned_files += 1
                file_findings = self.scan_file(file_path)
                findings.extend(file_findings)
        
        self.findings = findings
        return findings
    
    def scan_git_diff(self, repo_path: Path, base_ref: str = "HEAD~1") -> List[SecretFinding]:
        """Scan only changed files in git diff."""
        if not HAS_GIT:
            print("GitPython not installed. Cannot scan git diff.")
            return []
        
        findings = []
        
        try:
            repo = git.Repo(repo_path)
            diff = repo.git.diff(base_ref, name_only=True).splitlines()
            
            for file_path in diff:
                full_path = repo_path / file_path
                if full_path.exists() and full_path.is_file():
                    if full_path.suffix in self.config["scan_extensions"]:
                        file_findings = self.scan_file(full_path)
                        findings.extend(file_findings)
        
        except Exception as e:
            print(f"Error scanning git diff: {e}")
        
        return findings
    
    def generate_report(self, output_format: str = "json") -> str:
        """Generate a report of findings."""
        report_data = {
            "scan_timestamp": self.scan_start_time.isoformat() if self.scan_start_time else None,
            "scanned_files": self.scanned_files,
            "total_findings": len(self.findings),
            "findings_by_type": {},
            "findings_by_severity": {},
            "findings": []
        }
        
        # Group by type
        for finding in self.findings:
            type_name = finding.secret_type.value
            if type_name not in report_data["findings_by_type"]:
                report_data["findings_by_type"][type_name] = 0
            report_data["findings_by_type"][type_name] += 1
            
            # Group by severity
            if finding.severity not in report_data["findings_by_severity"]:
                report_data["findings_by_severity"][finding.severity] = 0
            report_data["findings_by_severity"][finding.severity] += 1
            
            # Add finding
            report_data["findings"].append(asdict(finding))
        
        if output_format == "json":
            return json.dumps(report_data, indent=2)
        elif output_format == "text":
            report = []
            report.append("=== Secret Scan Report ===")
            report.append(f"Scan Time: {report_data['scan_timestamp']}")
            report.append(f"Files Scanned: {report_data['scanned_files']}")
            report.append(f"Total Findings: {report_data['total_findings']}")
            report.append("\nFindings by Type:")
            for type_name, count in report_data["findings_by_type"].items():
                report.append(f"  {type_name}: {count}")
            report.append("\nFindings by Severity:")
            for severity, count in report_data["findings_by_severity"].items():
                report.append(f"  {severity}: {count}")
            report.append("\nDetailed Findings:")
            for finding in self.findings:
                report.append(f"\n[{finding.severity.upper()}] {finding.file_path}:{finding.line_number}")
                report.append(f"  Type: {finding.secret_type.value}")
                report.append(f"  Confidence: {finding.confidence:.2f}")
                report.append(f"  Context: {finding.context[:100]}...")
            
            return "\n".join(report)
        else:
            raise ValueError(f"Unknown output format: {output_format}")
    
    def export_sarif(self) -> Dict:
        """Export findings in SARIF format for GitHub integration."""
        sarif = {
            "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [{
                "tool": {
                    "driver": {
                        "name": "MEV-OG Secret Scanner",
                        "informationUri": "https://github.com/mev-og/scanner",
                        "version": "1.0.0",
                        "rules": []
                    }
                },
                "results": []
            }]
        }
        
        # Add rules
        for secret_type in SecretType:
            rule = {
                "id": secret_type.value,
                "name": secret_type.value.replace("_", " ").title(),
                "shortDescription": {
                    "text": f"Detects {secret_type.value} in code"
                },
                "defaultConfiguration": {
                    "level": self._get_severity(secret_type)
                }
            }
            sarif["runs"][0]["tool"]["driver"]["rules"].append(rule)
        
        # Add results
        for finding in self.findings:
            result = {
                "ruleId": finding.secret_type.value,
                "level": finding.severity,
                "message": {
                    "text": f"{finding.secret_type.value} detected with {finding.confidence:.0%} confidence"
                },
                "locations": [{
                    "physicalLocation": {
                        "artifactLocation": {
                            "uri": finding.file_path
                        },
                        "region": {
                            "startLine": finding.line_number,
                            "snippet": {
                                "text": finding.context
                            }
                        }
                    }
                }],
                "partialFingerprints": {
                    "secretHash": finding.hash
                }
            }
            sarif["runs"][0]["results"].append(result)
        
        return sarif


def main():
    """CLI interface for secret scanner."""
    parser = argparse.ArgumentParser(description="Scan for secrets in codebase")
    parser.add_argument("path", help="Path to scan (file or directory)")
    parser.add_argument("--config", help="Path to config file")
    parser.add_argument("--format", choices=["json", "text", "sarif"], default="text", help="Output format")
    parser.add_argument("--output", help="Output file (default: stdout)")
    parser.add_argument("--git-diff", action="store_true", help="Only scan git diff")
    parser.add_argument("--base-ref", default="HEAD~1", help="Base ref for git diff")
    parser.add_argument("--exit-code", action="store_true", help="Exit with non-zero code if secrets found")
    
    args = parser.parse_args()
    
    # Initialize scanner
    scanner = SecretScanner(config_path=args.config)
    
    # Perform scan
    scan_path = Path(args.path)
    
    if args.git_diff:
        findings = scanner.scan_git_diff(scan_path, args.base_ref)
    elif scan_path.is_file():
        findings = scanner.scan_file(scan_path)
    elif scan_path.is_dir():
        findings = scanner.scan_directory(scan_path)
    else:
        print(f"Error: {scan_path} is not a valid file or directory")
        sys.exit(1)
    
    # Generate report
    if args.format == "sarif":
        report = json.dumps(scanner.export_sarif(), indent=2)
    else:
        report = scanner.generate_report(args.format)
    
    # Output report
    if args.output:
        with open(args.output, "w") as f:
            f.write(report)
        print(f"Report written to {args.output}")
    else:
        print(report)
    
    # Exit code
    if args.exit_code and findings:
        sys.exit(1)


if __name__ == "__main__":
    main()
