"""
Safety evaluation system.

Monitors separation violations, calculates safety metrics, and generates reports.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import time

from .aircraft import Aircraft
from .airspace import Airspace, Conflict, SeparationRequirements
from .atc_system import ATCSystem, ATCInstruction


@dataclass
class SeparationViolation:
    """Record of a separation violation."""
    aircraft1: str
    aircraft2: str
    timestamp: float
    horizontal_separation: float  # nautical miles
    vertical_separation: float    # feet
    duration: float = 0.0  # seconds
    severity: str = "unknown"  # "critical", "major", "minor"


@dataclass
class NearMiss:
    """Record of a near miss event."""
    aircraft1: str
    aircraft2: str
    timestamp: float
    horizontal_separation: float
    vertical_separation: float
    min_separation_ratio: float  # ratio to minimum (e.g., 1.4 = 140% of minimum)


@dataclass
class SafetyMetrics:
    """Comprehensive safety metrics."""
    simulation_duration: float  # seconds
    total_aircraft: int
    
    # Separation violations
    violation_count: int = 0
    violation_duration_total: float = 0.0
    min_separation_achieved: float = float('inf')
    
    # Near misses
    near_miss_count: int = 0
    near_miss_rate: float = 0.0  # per 100 aircraft
    
    # Conflict resolution
    conflicts_detected: int = 0
    conflicts_resolved: int = 0
    avg_resolution_time: float = 0.0
    
    # Workload
    total_instructions: int = 0
    instructions_per_aircraft: float = 0.0
    
    # Efficiency
    avg_flight_efficiency: float = 0.0
    
    def to_dict(self) -> dict:
        """Convert metrics to dictionary."""
        return {
            'simulation_duration': self.simulation_duration,
            'total_aircraft': self.total_aircraft,
            'violations': {
                'count': self.violation_count,
                'total_duration': self.violation_duration_total,
                'min_separation': self.min_separation_achieved
            },
            'near_misses': {
                'count': self.near_miss_count,
                'rate_per_100': self.near_miss_rate
            },
            'conflict_resolution': {
                'detected': self.conflicts_detected,
                'resolved': self.conflicts_resolved,
                'avg_resolution_time': self.avg_resolution_time
            },
            'workload': {
                'total_instructions': self.total_instructions,
                'instructions_per_aircraft': self.instructions_per_aircraft
            },
            'efficiency': {
                'avg_flight_efficiency': self.avg_flight_efficiency
            }
        }


class SafetyEvaluator:
    """
    Evaluates safety of air traffic management.
    
    Monitors separation, tracks violations, and generates safety reports.
    """
    
    # Safety thresholds
    NEAR_MISS_THRESHOLD = 1.5  # 150% of minimum separation
    CRITICAL_VIOLATION_THRESHOLD = 0.5  # 50% of minimum separation
    
    def __init__(self, airspace: Airspace):
        self.airspace = airspace
        self.violations: List[SeparationViolation] = []
        self.near_misses: List[NearMiss] = []
        self.active_violations: Dict[tuple, SeparationViolation] = {}
        
        # Conflict tracking
        self.detected_conflicts: List[Conflict] = []
        self.conflict_resolution_times: List[float] = []
        
        # Statistics
        self.total_aircraft_seen = set()
        self.simulation_start_time = 0.0
        self.simulation_end_time = 0.0
    
    def update(
        self, 
        aircraft_list: List[Aircraft], 
        current_time: float,
        atc_system: Optional[ATCSystem] = None
    ):
        """
        Update safety monitoring.
        
        Args:
            aircraft_list: All aircraft to monitor
            current_time: Current simulation time
            atc_system: Optional ATC system for instruction tracking
        """
        if self.simulation_start_time == 0.0:
            self.simulation_start_time = current_time
        self.simulation_end_time = current_time
        
        # Track all aircraft
        for aircraft in aircraft_list:
            self.total_aircraft_seen.add(aircraft.callsign)
        
        # Check for separation violations
        self._check_violations(aircraft_list, current_time)
        
        # Check for near misses
        self._check_near_misses(aircraft_list, current_time)
        
        # Track conflicts
        if atc_system:
            self.detected_conflicts.extend(atc_system.airspace.conflicts)
    
    def _check_violations(self, aircraft_list: List[Aircraft], current_time: float):
        """Check for active separation violations."""
        current_violations = set()
        
        # Check each pair
        for i in range(len(aircraft_list)):
            for j in range(i + 1, len(aircraft_list)):
                ac1 = aircraft_list[i]
                ac2 = aircraft_list[j]
                
                if not self.airspace.is_separated(ac1, ac2):
                    pair_key = tuple(sorted([ac1.callsign, ac2.callsign]))
                    current_violations.add(pair_key)
                    
                    h_sep, v_sep = self.airspace.check_separation(ac1, ac2)
                    
                    # Track minimum separation
                    if h_sep < self.min_separation_achieved:
                        self.min_separation_achieved = h_sep
                    
                    # Check if new violation or continuing
                    if pair_key not in self.active_violations:
                        # New violation
                        severity = self._classify_violation_severity(h_sep, v_sep, ac1, ac2)
                        violation = SeparationViolation(
                            aircraft1=ac1.callsign,
                            aircraft2=ac2.callsign,
                            timestamp=current_time,
                            horizontal_separation=h_sep,
                            vertical_separation=v_sep,
                            severity=severity
                        )
                        self.active_violations[pair_key] = violation
                        self.violations.append(violation)
                    else:
                        # Update duration
                        self.active_violations[pair_key].duration += 1.0
        
        # Clear resolved violations
        resolved = set(self.active_violations.keys()) - current_violations
        for pair_key in resolved:
            del self.active_violations[pair_key]
    
    def _check_near_misses(self, aircraft_list: List[Aircraft], current_time: float):
        """Check for near miss events (close but not violating)."""
        for i in range(len(aircraft_list)):
            for j in range(i + 1, len(aircraft_list)):
                ac1 = aircraft_list[i]
                ac2 = aircraft_list[j]
                
                h_sep, v_sep = self.airspace.check_separation(ac1, ac2)
                avg_altitude = (ac1.position.altitude + ac2.position.altitude) / 2
                sep_req = SeparationRequirements.standard(avg_altitude)
                
                # Check if it's a near miss (close but not violating)
                if self.airspace.is_separated(ac1, ac2):
                    # Calculate separation ratio
                    h_ratio = h_sep / sep_req.horizontal_nm
                    v_ratio = v_sep / sep_req.vertical_ft if v_sep > 0 else float('inf')
                    min_ratio = min(h_ratio, v_ratio)
                    
                    if min_ratio < self.NEAR_MISS_THRESHOLD:
                        near_miss = NearMiss(
                            aircraft1=ac1.callsign,
                            aircraft2=ac2.callsign,
                            timestamp=current_time,
                            horizontal_separation=h_sep,
                            vertical_separation=v_sep,
                            min_separation_ratio=min_ratio
                        )
                        self.near_misses.append(near_miss)
    
    def _classify_violation_severity(
        self, 
        h_sep: float, 
        v_sep: float,
        ac1: Aircraft,
        ac2: Aircraft
    ) -> str:
        """Classify violation severity."""
        avg_altitude = (ac1.position.altitude + ac2.position.altitude) / 2
        sep_req = SeparationRequirements.standard(avg_altitude)
        
        # Calculate how close to minimum
        h_ratio = h_sep / sep_req.horizontal_nm
        
        if h_ratio < self.CRITICAL_VIOLATION_THRESHOLD:
            return "critical"
        elif h_ratio < 0.75:
            return "major"
        else:
            return "minor"
    
    @property
    def min_separation_achieved(self) -> float:
        """Get minimum separation achieved during simulation."""
        if not self.violations:
            return float('inf')
        return min(v.horizontal_separation for v in self.violations)
    
    @min_separation_achieved.setter
    def min_separation_achieved(self, value: float):
        """Track minimum separation (for internal use)."""
        pass  # Handled by property getter
    
    def calculate_metrics(self, atc_system: Optional[ATCSystem] = None) -> SafetyMetrics:
        """
        Calculate comprehensive safety metrics.
        
        Args:
            atc_system: Optional ATC system for instruction statistics
        """
        duration = self.simulation_end_time - self.simulation_start_time
        total_aircraft = len(self.total_aircraft_seen)
        
        metrics = SafetyMetrics(
            simulation_duration=duration,
            total_aircraft=total_aircraft
        )
        
        # Violation metrics
        metrics.violation_count = len(self.violations)
        metrics.violation_duration_total = sum(v.duration for v in self.violations)
        if self.violations:
            metrics.min_separation_achieved = min(v.horizontal_separation for v in self.violations)
        
        # Near miss metrics
        metrics.near_miss_count = len(self.near_misses)
        if total_aircraft > 0:
            metrics.near_miss_rate = (metrics.near_miss_count / total_aircraft) * 100
        
        # Conflict resolution metrics
        metrics.conflicts_detected = len(self.detected_conflicts)
        # Simplified: assume all conflicts were resolved if no violations
        metrics.conflicts_resolved = max(0, metrics.conflicts_detected - metrics.violation_count)
        
        # ATC workload metrics
        if atc_system:
            stats = atc_system.get_statistics()
            metrics.total_instructions = stats['total_instructions']
            if total_aircraft > 0:
                metrics.instructions_per_aircraft = metrics.total_instructions / total_aircraft
        
        return metrics
    
    def generate_report(self, atc_system: Optional[ATCSystem] = None) -> str:
        """
        Generate a comprehensive safety report.
        
        Returns:
            Formatted safety report as string
        """
        metrics = self.calculate_metrics(atc_system)
        
        report = []
        report.append("=" * 60)
        report.append("AIR TRAFFIC CONTROL SAFETY REPORT")
        report.append("=" * 60)
        report.append("")
        
        # Simulation overview
        report.append(f"Simulation Duration: {metrics.simulation_duration:.1f} seconds "
                     f"({metrics.simulation_duration/60:.1f} minutes)")
        report.append(f"Total Aircraft: {metrics.total_aircraft}")
        report.append("")
        
        # Separation violations
        report.append("SEPARATION VIOLATIONS")
        report.append("-" * 60)
        report.append(f"Total Violations: {metrics.violation_count}")
        report.append(f"Total Duration: {metrics.violation_duration_total:.1f} seconds")
        if metrics.violation_count > 0:
            report.append(f"Minimum Separation: {metrics.min_separation_achieved:.2f} NM")
            report.append("")
            report.append("Critical Violations:")
            critical = [v for v in self.violations if v.severity == "critical"]
            for v in critical[:5]:  # Show first 5
                report.append(f"  - {v.aircraft1} & {v.aircraft2}: "
                            f"{v.horizontal_separation:.2f} NM at t={v.timestamp:.0f}s")
        report.append("")
        
        # Near misses
        report.append("NEAR MISSES")
        report.append("-" * 60)
        report.append(f"Count: {metrics.near_miss_count}")
        report.append(f"Rate: {metrics.near_miss_rate:.2f} per 100 aircraft")
        report.append("")
        
        # Conflict resolution
        report.append("CONFLICT RESOLUTION")
        report.append("-" * 60)
        report.append(f"Conflicts Detected: {metrics.conflicts_detected}")
        report.append(f"Conflicts Resolved: {metrics.conflicts_resolved}")
        if metrics.conflicts_detected > 0:
            resolution_rate = (metrics.conflicts_resolved / metrics.conflicts_detected) * 100
            report.append(f"Resolution Rate: {resolution_rate:.1f}%")
        report.append("")
        
        # Workload
        report.append("CONTROLLER WORKLOAD")
        report.append("-" * 60)
        report.append(f"Total Instructions: {metrics.total_instructions}")
        report.append(f"Instructions per Aircraft: {metrics.instructions_per_aircraft:.2f}")
        report.append("")
        
        # Safety assessment
        report.append("SAFETY ASSESSMENT")
        report.append("-" * 60)
        safety_rating = self._calculate_safety_rating(metrics)
        report.append(f"Overall Safety Rating: {safety_rating}")
        report.append("")
        
        # Thresholds
        report.append("THRESHOLD CHECKS")
        report.append("-" * 60)
        
        if metrics.violation_count == 0:
            report.append("✓ No separation violations - PASS")
        else:
            report.append(f"✗ {metrics.violation_count} separation violations - FAIL")
        
        if metrics.near_miss_rate < 2.0:
            report.append(f"✓ Near miss rate {metrics.near_miss_rate:.1f}% < 2% - PASS")
        elif metrics.near_miss_rate < 5.0:
            report.append(f"⚠ Near miss rate {metrics.near_miss_rate:.1f}% < 5% - WARNING")
        else:
            report.append(f"✗ Near miss rate {metrics.near_miss_rate:.1f}% > 5% - FAIL")
        
        report.append("")
        report.append("=" * 60)
        
        return "\n".join(report)
    
    def _calculate_safety_rating(self, metrics: SafetyMetrics) -> str:
        """Calculate overall safety rating."""
        if metrics.violation_count > 0:
            return "UNSAFE"
        elif metrics.near_miss_rate > 5.0:
            return "MARGINAL"
        elif metrics.near_miss_rate > 2.0:
            return "ACCEPTABLE"
        else:
            return "SAFE"
    
    def compare_with_baseline(
        self, 
        baseline_metrics: SafetyMetrics,
        current_metrics: Optional[SafetyMetrics] = None
    ) -> str:
        """
        Compare current metrics with baseline (e.g., human controller).
        
        Args:
            baseline_metrics: Metrics from baseline system
            current_metrics: Current metrics (if None, calculate from current data)
            
        Returns:
            Comparison report as string
        """
        if current_metrics is None:
            current_metrics = self.calculate_metrics()
        
        report = []
        report.append("=" * 70)
        report.append("AUTOMATED vs BASELINE COMPARISON")
        report.append("=" * 70)
        report.append("")
        report.append(f"{'Metric':<35} | {'Auto':<12} | {'Baseline':<12} | Delta")
        report.append("-" * 70)
        
        # Format comparison rows
        def compare_row(name: str, auto_val: float, base_val: float, 
                       format_str: str = "{:.1f}", lower_better: bool = True):
            delta = auto_val - base_val
            delta_str = f"{delta:+.1f}" if isinstance(delta, float) else f"{delta:+d}"
            symbol = "↓" if (delta < 0 and lower_better) or (delta > 0 and not lower_better) else "↑"
            row = f"{name:<35} | {format_str.format(auto_val):<12} | {format_str.format(base_val):<12} | {delta_str} {symbol}"
            report.append(row)
        
        compare_row("Separation Violations", 
                   current_metrics.violation_count, 
                   baseline_metrics.violation_count,
                   "{:.0f}", True)
        compare_row("Near Misses", 
                   current_metrics.near_miss_count,
                   baseline_metrics.near_miss_count,
                   "{:.0f}", True)
        compare_row("Near Miss Rate (per 100)", 
                   current_metrics.near_miss_rate,
                   baseline_metrics.near_miss_rate,
                   "{:.2f}", True)
        compare_row("Instructions per Aircraft",
                   current_metrics.instructions_per_aircraft,
                   baseline_metrics.instructions_per_aircraft,
                   "{:.2f}", True)
        
        report.append("")
        report.append("=" * 70)
        
        return "\n".join(report)
