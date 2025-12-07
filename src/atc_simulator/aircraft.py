"""
Aircraft simulation module.

Implements realistic aircraft behavior including flight dynamics,
position tracking, and response to ATC instructions.
"""

import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from enum import Enum


class AircraftStatus(Enum):
    """Aircraft operational status."""
    TAXIING = "taxiing"
    DEPARTING = "departing"
    ENROUTE = "enroute"
    ARRIVING = "arriving"
    LANDED = "landed"


@dataclass
class Position:
    """3D position in airspace."""
    x: float  # nautical miles
    y: float  # nautical miles
    altitude: float  # feet
    
    def distance_to(self, other: 'Position') -> float:
        """Calculate horizontal distance to another position in nautical miles."""
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)
    
    def vertical_separation(self, other: 'Position') -> float:
        """Calculate vertical separation in feet."""
        return abs(self.altitude - other.altitude)


@dataclass
class Velocity:
    """Aircraft velocity vector."""
    speed: float  # knots
    heading: float  # degrees (0-360, 0=North)
    
    def normalize_heading(self):
        """Ensure heading is in 0-360 range."""
        self.heading = self.heading % 360


@dataclass
class Waypoint:
    """Navigation waypoint."""
    name: str
    x: float
    y: float
    altitude: Optional[float] = None  # Target altitude at waypoint (if specified)


class Aircraft:
    """
    Simulates an individual aircraft with realistic flight dynamics.
    
    Attributes:
        callsign: Unique aircraft identifier (e.g., "UAL123")
        position: Current 3D position
        velocity: Current speed and heading
        flight_plan: List of waypoints to follow
        aircraft_type: Aircraft model (e.g., "B737")
        status: Current flight phase
    """
    
    # Aircraft performance constraints
    MAX_CLIMB_RATE = 2000  # feet per minute
    MAX_DESCENT_RATE = 2000  # feet per minute
    MAX_TURN_RATE = 3.0  # degrees per second
    MAX_SPEED_CHANGE = 10.0  # knots per second
    MIN_ALTITUDE = 1000  # feet AGL
    MAX_ALTITUDE = 45000  # feet
    MIN_SPEED = 120  # knots
    MAX_SPEED = 550  # knots
    
    def __init__(
        self,
        callsign: str,
        position: Position,
        velocity: Velocity,
        flight_plan: List[Waypoint],
        aircraft_type: str = "B737",
        status: AircraftStatus = AircraftStatus.ENROUTE
    ):
        self.callsign = callsign
        self.position = position
        self.velocity = velocity
        self.flight_plan = flight_plan
        self.aircraft_type = aircraft_type
        self.status = status
        
        # ATC instructions
        self.target_altitude: Optional[float] = None
        self.target_heading: Optional[float] = None
        self.target_speed: Optional[float] = None
        
        # State tracking
        self.current_waypoint_index = 0
        self.time_in_simulation = 0.0  # seconds
    
    def update(self, time_delta: float = 1.0):
        """
        Update aircraft state for one time step.
        
        Args:
            time_delta: Time step in seconds (default 1.0 for 1 Hz update)
        """
        self.time_in_simulation += time_delta
        
        # Update altitude
        self._update_altitude(time_delta)
        
        # Update heading
        self._update_heading(time_delta)
        
        # Update speed
        self._update_speed(time_delta)
        
        # Update position based on velocity
        self._update_position(time_delta)
        
        # Check waypoint progress
        self._check_waypoint_progress()
    
    def _update_altitude(self, time_delta: float):
        """Update altitude towards target."""
        if self.target_altitude is None:
            # Follow flight plan altitude if at waypoint
            if self.current_waypoint_index < len(self.flight_plan):
                wp = self.flight_plan[self.current_waypoint_index]
                if wp.altitude is not None:
                    self.target_altitude = wp.altitude
            return
        
        altitude_diff = self.target_altitude - self.position.altitude
        
        if abs(altitude_diff) < 10:  # Within 10 feet
            self.position.altitude = self.target_altitude
            self.target_altitude = None
            return
        
        # Calculate climb/descent rate
        max_change = (self.MAX_CLIMB_RATE if altitude_diff > 0 else self.MAX_DESCENT_RATE) * (time_delta / 60.0)
        
        if abs(altitude_diff) <= max_change:
            self.position.altitude = self.target_altitude
            self.target_altitude = None
        else:
            self.position.altitude += max_change if altitude_diff > 0 else -max_change
        
        # Enforce altitude limits
        self.position.altitude = max(self.MIN_ALTITUDE, min(self.MAX_ALTITUDE, self.position.altitude))
    
    def _update_heading(self, time_delta: float):
        """Update heading towards target."""
        if self.target_heading is None:
            # Navigate to next waypoint if available
            if self.current_waypoint_index < len(self.flight_plan):
                wp = self.flight_plan[self.current_waypoint_index]
                self.target_heading = self._calculate_heading_to_waypoint(wp)
            return
        
        heading_diff = self._shortest_heading_difference(self.velocity.heading, self.target_heading)
        
        if abs(heading_diff) < 0.5:  # Within 0.5 degrees
            self.velocity.heading = self.target_heading
            self.target_heading = None
            return
        
        # Calculate turn
        max_turn = self.MAX_TURN_RATE * time_delta
        
        if abs(heading_diff) <= max_turn:
            self.velocity.heading = self.target_heading
            self.target_heading = None
        else:
            self.velocity.heading += max_turn if heading_diff > 0 else -max_turn
        
        self.velocity.normalize_heading()
    
    def _update_speed(self, time_delta: float):
        """Update speed towards target."""
        if self.target_speed is None:
            return
        
        speed_diff = self.target_speed - self.velocity.speed
        
        if abs(speed_diff) < 1:  # Within 1 knot
            self.velocity.speed = self.target_speed
            self.target_speed = None
            return
        
        max_change = self.MAX_SPEED_CHANGE * time_delta
        
        if abs(speed_diff) <= max_change:
            self.velocity.speed = self.target_speed
            self.target_speed = None
        else:
            self.velocity.speed += max_change if speed_diff > 0 else -max_change
        
        # Enforce speed limits
        self.velocity.speed = max(self.MIN_SPEED, min(self.MAX_SPEED, self.velocity.speed))
    
    def _update_position(self, time_delta: float):
        """Update position based on current velocity."""
        # Convert speed (knots) to nautical miles per second
        distance = self.velocity.speed * (time_delta / 3600.0)
        
        # Convert heading to radians (0 degrees = North = +Y axis)
        heading_rad = math.radians(self.velocity.heading)
        
        # Update position (heading 0 = North = +Y, heading 90 = East = +X)
        self.position.x += distance * math.sin(heading_rad)
        self.position.y += distance * math.cos(heading_rad)
    
    def _check_waypoint_progress(self):
        """Check if aircraft has reached current waypoint."""
        if self.current_waypoint_index >= len(self.flight_plan):
            return
        
        wp = self.flight_plan[self.current_waypoint_index]
        distance = math.sqrt((self.position.x - wp.x) ** 2 + (self.position.y - wp.y) ** 2)
        
        # Consider waypoint reached if within 1 nautical mile
        if distance < 1.0:
            self.current_waypoint_index += 1
    
    def _calculate_heading_to_waypoint(self, waypoint: Waypoint) -> float:
        """Calculate heading to a waypoint."""
        dx = waypoint.x - self.position.x
        dy = waypoint.y - self.position.y
        
        # Calculate angle (atan2 gives angle from +X axis)
        angle_rad = math.atan2(dx, dy)
        heading = math.degrees(angle_rad)
        
        # Normalize to 0-360
        return heading % 360
    
    @staticmethod
    def _shortest_heading_difference(current: float, target: float) -> float:
        """
        Calculate shortest angular difference between headings.
        Positive means turn right, negative means turn left.
        """
        diff = target - current
        
        # Normalize to -180 to +180
        while diff > 180:
            diff -= 360
        while diff < -180:
            diff += 360
        
        return diff
    
    def set_altitude(self, altitude: float):
        """Set target altitude via ATC instruction."""
        self.target_altitude = max(self.MIN_ALTITUDE, min(self.MAX_ALTITUDE, altitude))
    
    def set_heading(self, heading: float):
        """Set target heading via ATC instruction."""
        self.target_heading = heading % 360
    
    def set_speed(self, speed: float):
        """Set target speed via ATC instruction."""
        self.target_speed = max(self.MIN_SPEED, min(self.MAX_SPEED, speed))
    
    def get_state(self) -> dict:
        """Get current aircraft state as dictionary."""
        return {
            'callsign': self.callsign,
            'position': {
                'x': self.position.x,
                'y': self.position.y,
                'altitude': self.position.altitude
            },
            'velocity': {
                'speed': self.velocity.speed,
                'heading': self.velocity.heading
            },
            'aircraft_type': self.aircraft_type,
            'status': self.status.value,
            'target_altitude': self.target_altitude,
            'target_heading': self.target_heading,
            'target_speed': self.target_speed,
            'current_waypoint': self.current_waypoint_index
        }
    
    def predict_position(self, time_ahead: float) -> Position:
        """
        Predict future position assuming constant velocity.
        
        Args:
            time_ahead: Time in seconds to predict ahead
            
        Returns:
            Predicted Position
        """
        distance = self.velocity.speed * (time_ahead / 3600.0)
        heading_rad = math.radians(self.velocity.heading)
        
        return Position(
            x=self.position.x + distance * math.sin(heading_rad),
            y=self.position.y + distance * math.cos(heading_rad),
            altitude=self.position.altitude  # Assume constant altitude for prediction
        )
    
    def __repr__(self):
        return (f"Aircraft({self.callsign}, pos=({self.position.x:.1f}, {self.position.y:.1f}, "
                f"{self.position.altitude:.0f}ft), spd={self.velocity.speed:.0f}kt, "
                f"hdg={self.velocity.heading:.0f}°)")
