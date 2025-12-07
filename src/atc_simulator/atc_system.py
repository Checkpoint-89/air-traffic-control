"""
Automated Air Traffic Control system.

Generates ATC instructions to resolve conflicts and manage traffic.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict
from enum import Enum
import time

from .aircraft import Aircraft
from .airspace import Airspace, Conflict, SeparationRequirements


class InstructionType(Enum):
    """Types of ATC instructions."""
    ALTITUDE_CHANGE = "altitude_change"
    HEADING_CHANGE = "heading_change"
    SPEED_CHANGE = "speed_change"
    HOLD = "hold"
    DIRECT_TO = "direct_to"
    CLEARED_APPROACH = "cleared_approach"


class Priority(Enum):
    """Instruction priority levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ATCInstruction:
    """ATC instruction to an aircraft."""
    callsign: str
    timestamp: float
    instruction_type: InstructionType
    parameters: Dict
    reason: str
    priority: Priority
    
    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            'callsign': self.callsign,
            'timestamp': self.timestamp,
            'instruction_type': self.instruction_type.value,
            'parameters': self.parameters,
            'reason': self.reason,
            'priority': self.priority.value
        }


class ATCSystem:
    """
    Automated Air Traffic Control system.
    
    Detects conflicts and generates instructions to resolve them.
    """
    
    def __init__(self, airspace: Airspace):
        self.airspace = airspace
        self.instructions: List[ATCInstruction] = []
        self.instruction_count = 0
    
    def update(self, aircraft_list: List[Aircraft], current_time: float):
        """
        Main update cycle for ATC system.
        
        Args:
            aircraft_list: All aircraft under control
            current_time: Current simulation time in seconds
        """
        # Detect conflicts
        conflicts = self.airspace.detect_conflicts(aircraft_list, lookahead_time=300.0)
        
        # Resolve conflicts
        for conflict in conflicts:
            if conflict.severity in ["high", "medium"]:
                self._resolve_conflict(conflict, aircraft_list, current_time)
    
    def _resolve_conflict(
        self, 
        conflict: Conflict, 
        aircraft_list: List[Aircraft],
        current_time: float
    ):
        """
        Generate instructions to resolve a conflict.
        
        Strategy priority:
        1. Altitude change (preferred for enroute)
        2. Heading change (vector around)
        3. Speed change (temporal separation)
        """
        # Find the aircraft objects
        ac1 = next((ac for ac in aircraft_list if ac.callsign == conflict.aircraft1), None)
        ac2 = next((ac for ac in aircraft_list if ac.callsign == conflict.aircraft2), None)
        
        if not ac1 or not ac2:
            return
        
        # Check if already issued instructions for this pair recently
        if self._recently_instructed(conflict.aircraft1, conflict.aircraft2, current_time):
            return
        
        # Try altitude separation first
        if self._try_altitude_resolution(ac1, ac2, conflict, current_time):
            return
        
        # Try heading change
        if self._try_heading_resolution(ac1, ac2, conflict, current_time):
            return
        
        # Fall back to speed adjustment
        self._try_speed_resolution(ac1, ac2, conflict, current_time)
    
    def _try_altitude_resolution(
        self, 
        ac1: Aircraft, 
        ac2: Aircraft,
        conflict: Conflict,
        current_time: float
    ) -> bool:
        """
        Attempt to resolve conflict by altitude change.
        
        Returns True if instruction issued.
        """
        # Get separation requirements
        avg_altitude = (ac1.position.altitude + ac2.position.altitude) / 2
        sep_req = SeparationRequirements.standard(avg_altitude)
        
        # Determine which aircraft to move
        # Prefer moving the lower aircraft up or higher aircraft down
        if ac1.position.altitude < ac2.position.altitude:
            lower_ac = ac1
            higher_ac = ac2
        else:
            lower_ac = ac2
            higher_ac = ac1
        
        # Try to climb lower aircraft
        new_altitude = lower_ac.position.altitude - sep_req.vertical_ft - 1000
        if new_altitude >= Aircraft.MIN_ALTITUDE:
            instruction = ATCInstruction(
                callsign=lower_ac.callsign,
                timestamp=current_time,
                instruction_type=InstructionType.ALTITUDE_CHANGE,
                parameters={'new_altitude': new_altitude, 'rate': 'normal'},
                reason='traffic_conflict',
                priority=Priority.HIGH if conflict.severity == "high" else Priority.MEDIUM
            )
            self._issue_instruction(instruction, lower_ac)
            return True
        
        # Try to descend higher aircraft
        new_altitude = higher_ac.position.altitude + sep_req.vertical_ft + 1000
        if new_altitude <= Aircraft.MAX_ALTITUDE:
            instruction = ATCInstruction(
                callsign=higher_ac.callsign,
                timestamp=current_time,
                instruction_type=InstructionType.ALTITUDE_CHANGE,
                parameters={'new_altitude': new_altitude, 'rate': 'normal'},
                reason='traffic_conflict',
                priority=Priority.HIGH if conflict.severity == "high" else Priority.MEDIUM
            )
            self._issue_instruction(instruction, higher_ac)
            return True
        
        return False
    
    def _try_heading_resolution(
        self, 
        ac1: Aircraft, 
        ac2: Aircraft,
        conflict: Conflict,
        current_time: float
    ) -> bool:
        """
        Attempt to resolve conflict by heading change.
        
        Returns True if instruction issued.
        """
        # Vector the first aircraft 30 degrees right
        new_heading = (ac1.velocity.heading + 30) % 360
        
        instruction = ATCInstruction(
            callsign=ac1.callsign,
            timestamp=current_time,
            instruction_type=InstructionType.HEADING_CHANGE,
            parameters={'new_heading': new_heading},
            reason='traffic_conflict',
            priority=Priority.HIGH if conflict.severity == "high" else Priority.MEDIUM
        )
        self._issue_instruction(instruction, ac1)
        return True
    
    def _try_speed_resolution(
        self, 
        ac1: Aircraft, 
        ac2: Aircraft,
        conflict: Conflict,
        current_time: float
    ) -> bool:
        """
        Attempt to resolve conflict by speed change.
        
        Returns True if instruction issued.
        """
        # Slow down the faster aircraft or speed up the slower one
        if ac1.velocity.speed > ac2.velocity.speed:
            new_speed = max(Aircraft.MIN_SPEED, ac1.velocity.speed - 50)
            target_ac = ac1
        else:
            new_speed = min(Aircraft.MAX_SPEED, ac2.velocity.speed + 50)
            target_ac = ac2
        
        instruction = ATCInstruction(
            callsign=target_ac.callsign,
            timestamp=current_time,
            instruction_type=InstructionType.SPEED_CHANGE,
            parameters={'new_speed': new_speed},
            reason='traffic_conflict',
            priority=Priority.MEDIUM
        )
        self._issue_instruction(instruction, target_ac)
        return True
    
    def _issue_instruction(self, instruction: ATCInstruction, aircraft: Aircraft):
        """
        Issue instruction to aircraft and record it.
        """
        self.instructions.append(instruction)
        self.instruction_count += 1
        
        # Apply instruction to aircraft
        if instruction.instruction_type == InstructionType.ALTITUDE_CHANGE:
            aircraft.set_altitude(instruction.parameters['new_altitude'])
        elif instruction.instruction_type == InstructionType.HEADING_CHANGE:
            aircraft.set_heading(instruction.parameters['new_heading'])
        elif instruction.instruction_type == InstructionType.SPEED_CHANGE:
            aircraft.set_speed(instruction.parameters['new_speed'])
    
    def _recently_instructed(
        self, 
        callsign1: str, 
        callsign2: str, 
        current_time: float,
        window: float = 60.0
    ) -> bool:
        """
        Check if instructions were recently issued for this aircraft pair.
        
        Args:
            window: Time window in seconds to check
        """
        for instruction in reversed(self.instructions[-20:]):  # Check last 20 instructions
            if current_time - instruction.timestamp > window:
                break
            if instruction.callsign in [callsign1, callsign2]:
                return True
        return False
    
    def get_instructions_for_aircraft(self, callsign: str) -> List[ATCInstruction]:
        """Get all instructions issued to a specific aircraft."""
        return [inst for inst in self.instructions if inst.callsign == callsign]
    
    def get_recent_instructions(self, time_window: float = 300.0) -> List[ATCInstruction]:
        """
        Get instructions issued within the time window.
        
        Args:
            time_window: Time in seconds to look back
        """
        if not self.instructions:
            return []
        
        current_time = self.instructions[-1].timestamp if self.instructions else 0
        return [inst for inst in self.instructions 
                if current_time - inst.timestamp <= time_window]
    
    def get_statistics(self) -> dict:
        """Get ATC system statistics."""
        if not self.instructions:
            return {
                'total_instructions': 0,
                'by_type': {},
                'by_priority': {}
            }
        
        by_type = {}
        by_priority = {}
        
        for instruction in self.instructions:
            inst_type = instruction.instruction_type.value
            priority = instruction.priority.value
            
            by_type[inst_type] = by_type.get(inst_type, 0) + 1
            by_priority[priority] = by_priority.get(priority, 0) + 1
        
        return {
            'total_instructions': len(self.instructions),
            'by_type': by_type,
            'by_priority': by_priority
        }
    
    def clear_old_instructions(self, before_time: float):
        """Clear instructions older than specified time to save memory."""
        self.instructions = [inst for inst in self.instructions 
                           if inst.timestamp >= before_time]
