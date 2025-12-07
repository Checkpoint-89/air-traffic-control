"""
Airspace management module.

Defines controlled airspace, separation requirements, and conflict detection.
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional
from enum import Enum

from .aircraft import Aircraft, Position


class AirspaceClass(Enum):
    """Airspace classification."""
    CLASS_A = "A"  # 18,000 - 60,000 ft
    CLASS_B = "B"  # Surface - 10,000 ft (major airports)
    CLASS_C = "C"  # Surface - 4,000 ft (medium airports)
    CLASS_E = "E"  # 1,200 - 18,000 ft (enroute)


@dataclass
class SeparationRequirements:
    """Minimum separation standards."""
    horizontal_nm: float  # Nautical miles
    vertical_ft: float    # Feet
    
    @staticmethod
    def standard(altitude: float) -> 'SeparationRequirements':
        """Get standard separation requirements based on altitude."""
        if altitude < 29000:  # Below FL290
            return SeparationRequirements(horizontal_nm=5.0, vertical_ft=1000.0)
        else:  # Above FL290
            return SeparationRequirements(horizontal_nm=5.0, vertical_ft=2000.0)
    
    @staticmethod
    def terminal() -> 'SeparationRequirements':
        """Get terminal area separation requirements (reduced)."""
        return SeparationRequirements(horizontal_nm=3.0, vertical_ft=1000.0)


@dataclass
class Sector:
    """Airspace sector definition."""
    name: str
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    altitude_min: float
    altitude_max: float
    max_aircraft: int = 20
    
    def contains(self, position: Position) -> bool:
        """Check if position is within sector boundaries."""
        return (self.x_min <= position.x <= self.x_max and
                self.y_min <= position.y <= self.y_max and
                self.altitude_min <= position.altitude <= self.altitude_max)


@dataclass
class Conflict:
    """Detected conflict between aircraft."""
    aircraft1: str  # callsign
    aircraft2: str  # callsign
    time_to_cpa: float  # seconds to closest point of approach
    horizontal_separation_at_cpa: float  # nautical miles
    vertical_separation_at_cpa: float  # feet
    severity: str  # "high", "medium", "low"
    
    def is_violation(self, sep_requirements: SeparationRequirements) -> bool:
        """Check if this conflict constitutes a separation violation."""
        return (self.horizontal_separation_at_cpa < sep_requirements.horizontal_nm and
                self.vertical_separation_at_cpa < sep_requirements.vertical_ft)


class Airspace:
    """
    Manages airspace structure, sectors, and separation monitoring.
    
    Provides conflict detection and separation verification.
    """
    
    def __init__(self):
        self.sectors: List[Sector] = []
        self.conflicts: List[Conflict] = []
    
    def add_sector(self, sector: Sector):
        """Add a sector to the airspace."""
        self.sectors.append(sector)
    
    def get_sector(self, position: Position) -> Optional[Sector]:
        """Find which sector contains the given position."""
        for sector in self.sectors:
            if sector.contains(position):
                return sector
        return None
    
    def check_separation(self, aircraft1: Aircraft, aircraft2: Aircraft) -> Tuple[float, float]:
        """
        Check current separation between two aircraft.
        
        Returns:
            Tuple of (horizontal_separation_nm, vertical_separation_ft)
        """
        horizontal = aircraft1.position.distance_to(aircraft2.position)
        vertical = aircraft1.position.vertical_separation(aircraft2.position)
        return horizontal, vertical
    
    def is_separated(self, aircraft1: Aircraft, aircraft2: Aircraft) -> bool:
        """
        Check if two aircraft meet separation requirements.
        
        Returns:
            True if properly separated, False if violation
        """
        horizontal, vertical = self.check_separation(aircraft1, aircraft2)
        
        # Get appropriate separation requirements
        avg_altitude = (aircraft1.position.altitude + aircraft2.position.altitude) / 2
        sep_req = SeparationRequirements.standard(avg_altitude)
        
        # Both horizontal OR vertical separation must be satisfied
        return horizontal >= sep_req.horizontal_nm or vertical >= sep_req.vertical_ft
    
    def detect_conflicts(
        self, 
        aircraft_list: List[Aircraft], 
        lookahead_time: float = 300.0
    ) -> List[Conflict]:
        """
        Detect potential conflicts between aircraft.
        
        Args:
            aircraft_list: List of aircraft to check
            lookahead_time: Time in seconds to look ahead (default 300s = 5 minutes)
            
        Returns:
            List of detected conflicts
        """
        conflicts = []
        
        # Check each pair of aircraft
        for i in range(len(aircraft_list)):
            for j in range(i + 1, len(aircraft_list)):
                conflict = self._check_pair_for_conflict(
                    aircraft_list[i], 
                    aircraft_list[j], 
                    lookahead_time
                )
                if conflict:
                    conflicts.append(conflict)
        
        self.conflicts = conflicts
        return conflicts
    
    def _check_pair_for_conflict(
        self, 
        aircraft1: Aircraft, 
        aircraft2: Aircraft,
        lookahead_time: float
    ) -> Optional[Conflict]:
        """
        Check if two aircraft will have a conflict.
        
        Uses simple trajectory prediction assuming constant velocity.
        """
        # Sample points in time to find closest approach
        min_horizontal = float('inf')
        min_vertical = float('inf')
        time_at_min = 0
        
        time_steps = int(lookahead_time)  # Check every second
        
        for t in range(time_steps):
            pos1 = aircraft1.predict_position(t)
            pos2 = aircraft2.predict_position(t)
            
            h_sep = pos1.distance_to(pos2)
            v_sep = abs(pos1.altitude - pos2.altitude)
            
            # Track minimum separation
            if h_sep < min_horizontal:
                min_horizontal = h_sep
                min_vertical = v_sep
                time_at_min = t
        
        # Determine if this is a conflict
        avg_altitude = (aircraft1.position.altitude + aircraft2.position.altitude) / 2
        sep_req = SeparationRequirements.standard(avg_altitude)
        
        # Check if separation will be violated
        if min_horizontal < sep_req.horizontal_nm and min_vertical < sep_req.vertical_ft:
            # Determine severity
            severity = self._calculate_severity(
                min_horizontal, 
                min_vertical, 
                time_at_min, 
                sep_req
            )
            
            return Conflict(
                aircraft1=aircraft1.callsign,
                aircraft2=aircraft2.callsign,
                time_to_cpa=time_at_min,
                horizontal_separation_at_cpa=min_horizontal,
                vertical_separation_at_cpa=min_vertical,
                severity=severity
            )
        
        return None
    
    def _calculate_severity(
        self,
        h_sep: float,
        v_sep: float,
        time_to_cpa: float,
        sep_req: SeparationRequirements
    ) -> str:
        """Calculate conflict severity based on separation and time."""
        # High severity: very close or imminent
        if time_to_cpa < 60 or h_sep < sep_req.horizontal_nm * 0.5:
            return "high"
        
        # Medium severity: moderate time or separation
        if time_to_cpa < 180 or h_sep < sep_req.horizontal_nm * 0.75:
            return "medium"
        
        # Low severity: sufficient time to resolve
        return "low"
    
    def get_conflicts_for_aircraft(self, callsign: str) -> List[Conflict]:
        """Get all conflicts involving a specific aircraft."""
        return [c for c in self.conflicts 
                if c.aircraft1 == callsign or c.aircraft2 == callsign]
    
    def get_aircraft_in_sector(
        self, 
        sector: Sector, 
        aircraft_list: List[Aircraft]
    ) -> List[Aircraft]:
        """Get all aircraft currently in a specific sector."""
        return [ac for ac in aircraft_list if sector.contains(ac.position)]
    
    def is_sector_full(self, sector: Sector, aircraft_list: List[Aircraft]) -> bool:
        """Check if sector has reached maximum aircraft capacity."""
        aircraft_in_sector = self.get_aircraft_in_sector(sector, aircraft_list)
        return len(aircraft_in_sector) >= sector.max_aircraft
    
    def create_default_sectors(self, x_range: Tuple[float, float], y_range: Tuple[float, float]):
        """
        Create a default sector layout covering the specified area.
        
        Args:
            x_range: (min_x, max_x) in nautical miles
            y_range: (min_y, max_y) in nautical miles
        """
        # Create high and low altitude sectors
        self.add_sector(Sector(
            name="HIGH_WEST",
            x_min=x_range[0],
            x_max=(x_range[0] + x_range[1]) / 2,
            y_min=y_range[0],
            y_max=y_range[1],
            altitude_min=18000,
            altitude_max=45000
        ))
        
        self.add_sector(Sector(
            name="HIGH_EAST",
            x_min=(x_range[0] + x_range[1]) / 2,
            x_max=x_range[1],
            y_min=y_range[0],
            y_max=y_range[1],
            altitude_min=18000,
            altitude_max=45000
        ))
        
        self.add_sector(Sector(
            name="LOW_WEST",
            x_min=x_range[0],
            x_max=(x_range[0] + x_range[1]) / 2,
            y_min=y_range[0],
            y_max=y_range[1],
            altitude_min=1000,
            altitude_max=18000
        ))
        
        self.add_sector(Sector(
            name="LOW_EAST",
            x_min=(x_range[0] + x_range[1]) / 2,
            x_max=x_range[1],
            y_min=y_range[0],
            y_max=y_range[1],
            altitude_min=1000,
            altitude_max=18000
        ))
