"""
Main air traffic simulator.

Orchestrates aircraft, airspace, ATC system, and safety evaluation.
"""

from typing import List, Optional, Callable
import random

from .aircraft import Aircraft, Position, Velocity, Waypoint, AircraftStatus
from .airspace import Airspace
from .atc_system import ATCSystem
from .safety_evaluator import SafetyEvaluator, SafetyMetrics


class Simulator:
    """
    Main air traffic control simulator.
    
    Orchestrates all components and runs simulation scenarios.
    """
    
    def __init__(
        self,
        airspace: Optional[Airspace] = None,
        update_frequency: float = 1.0  # Hz
    ):
        """
        Initialize simulator.
        
        Args:
            airspace: Airspace to use (creates default if None)
            update_frequency: Simulation update rate in Hz
        """
        self.airspace = airspace or Airspace()
        self.atc_system = ATCSystem(self.airspace)
        self.safety_evaluator = SafetyEvaluator(self.airspace)
        
        self.aircraft: List[Aircraft] = []
        self.current_time = 0.0
        self.update_frequency = update_frequency
        self.time_step = 1.0 / update_frequency
        
        # Callbacks for monitoring
        self.on_conflict_detected: Optional[Callable] = None
        self.on_violation: Optional[Callable] = None
    
    def add_aircraft(self, aircraft: Aircraft):
        """Add an aircraft to the simulation."""
        self.aircraft.append(aircraft)
    
    def remove_aircraft(self, callsign: str):
        """Remove an aircraft from the simulation."""
        self.aircraft = [ac for ac in self.aircraft if ac.callsign != callsign]
    
    def get_aircraft(self, callsign: str) -> Optional[Aircraft]:
        """Get aircraft by callsign."""
        for ac in self.aircraft:
            if ac.callsign == callsign:
                return ac
        return None
    
    def step(self):
        """Execute one simulation step."""
        # Update all aircraft
        for aircraft in self.aircraft:
            aircraft.update(self.time_step)
        
        # Update ATC system (detect conflicts and issue instructions)
        self.atc_system.update(self.aircraft, self.current_time)
        
        # Update safety monitoring
        self.safety_evaluator.update(self.aircraft, self.current_time, self.atc_system)
        
        # Advance time
        self.current_time += self.time_step
    
    def run(self, duration: float, verbose: bool = False):
        """
        Run simulation for specified duration.
        
        Args:
            duration: Simulation duration in seconds
            verbose: Print progress updates
        """
        steps = int(duration / self.time_step)
        
        for i in range(steps):
            self.step()
            
            if verbose and i % 60 == 0:  # Print every minute
                print(f"Simulation time: {self.current_time:.0f}s "
                      f"({self.current_time/60:.1f} min), "
                      f"Aircraft: {len(self.aircraft)}")
        
        if verbose:
            print(f"\nSimulation completed: {duration}s ({duration/60:.1f} min)")
    
    def get_metrics(self) -> SafetyMetrics:
        """Get current safety metrics."""
        return self.safety_evaluator.calculate_metrics(self.atc_system)
    
    def generate_report(self) -> str:
        """Generate safety evaluation report."""
        return self.safety_evaluator.generate_report(self.atc_system)
    
    def reset(self):
        """Reset simulation to initial state."""
        self.aircraft.clear()
        self.current_time = 0.0
        self.atc_system = ATCSystem(self.airspace)
        self.safety_evaluator = SafetyEvaluator(self.airspace)
    
    def create_default_airspace(self, size: float = 200.0):
        """
        Create a default airspace configuration.
        
        Args:
            size: Airspace size in nautical miles (square)
        """
        self.airspace.create_default_sectors(
            x_range=(0, size),
            y_range=(0, size)
        )
    
    def generate_random_traffic(
        self, 
        num_aircraft: int,
        airspace_size: float = 200.0,
        min_altitude: float = 20000,
        max_altitude: float = 40000,
        min_speed: float = 350,
        max_speed: float = 500
    ):
        """
        Generate random traffic pattern.
        
        Args:
            num_aircraft: Number of aircraft to generate
            airspace_size: Size of airspace in nautical miles
            min_altitude: Minimum cruise altitude
            max_altitude: Maximum cruise altitude
            min_speed: Minimum speed in knots
            max_speed: Maximum speed in knots
        """
        airlines = ["UAL", "AAL", "DAL", "SWA", "JBU", "ASA", "FFT"]
        
        for i in range(num_aircraft):
            # Generate callsign
            airline = random.choice(airlines)
            flight_num = random.randint(100, 999)
            callsign = f"{airline}{flight_num}"
            
            # Random position
            position = Position(
                x=random.uniform(0, airspace_size),
                y=random.uniform(0, airspace_size),
                altitude=random.uniform(min_altitude, max_altitude)
            )
            
            # Random velocity
            velocity = Velocity(
                speed=random.uniform(min_speed, max_speed),
                heading=random.uniform(0, 360)
            )
            
            # Generate simple flight plan (2-3 waypoints)
            num_waypoints = random.randint(2, 3)
            flight_plan = []
            for j in range(num_waypoints):
                wp = Waypoint(
                    name=f"WP{i}_{j}",
                    x=random.uniform(0, airspace_size),
                    y=random.uniform(0, airspace_size),
                    altitude=random.uniform(min_altitude, max_altitude)
                )
                flight_plan.append(wp)
            
            # Create aircraft
            aircraft = Aircraft(
                callsign=callsign,
                position=position,
                velocity=velocity,
                flight_plan=flight_plan,
                aircraft_type=random.choice(["B737", "A320", "B777", "A350"]),
                status=AircraftStatus.ENROUTE
            )
            
            self.add_aircraft(aircraft)
    
    def create_conflict_scenario(self):
        """
        Create a scenario designed to test conflict detection and resolution.
        
        Two aircraft on collision course.
        """
        # Aircraft 1: Flying east
        ac1 = Aircraft(
            callsign="UAL100",
            position=Position(x=50, y=100, altitude=35000),
            velocity=Velocity(speed=450, heading=90),  # East
            flight_plan=[Waypoint("DEST1", 150, 100, 35000)],
            aircraft_type="B737"
        )
        
        # Aircraft 2: Flying west
        ac2 = Aircraft(
            callsign="AAL200",
            position=Position(x=150, y=100, altitude=35000),
            velocity=Velocity(speed=450, heading=270),  # West
            flight_plan=[Waypoint("DEST2", 50, 100, 35000)],
            aircraft_type="A320"
        )
        
        self.add_aircraft(ac1)
        self.add_aircraft(ac2)
    
    def create_high_density_scenario(self, num_aircraft: int = 50):
        """
        Create a high-density traffic scenario for stress testing.
        
        Args:
            num_aircraft: Number of aircraft (default 50)
        """
        self.generate_random_traffic(
            num_aircraft=num_aircraft,
            airspace_size=150,  # Smaller airspace for higher density
            min_altitude=30000,
            max_altitude=38000  # Narrower altitude range
        )
    
    def get_status(self) -> dict:
        """Get current simulation status."""
        return {
            'current_time': self.current_time,
            'num_aircraft': len(self.aircraft),
            'active_conflicts': len(self.atc_system.airspace.conflicts),
            'total_instructions': self.atc_system.instruction_count,
            'violations': len(self.safety_evaluator.violations),
            'near_misses': len(self.safety_evaluator.near_misses)
        }
    
    def print_status(self):
        """Print current simulation status."""
        status = self.get_status()
        print(f"\n{'='*60}")
        print(f"Simulation Time: {status['current_time']:.1f}s "
              f"({status['current_time']/60:.1f} min)")
        print(f"Aircraft: {status['num_aircraft']}")
        print(f"Active Conflicts: {status['active_conflicts']}")
        print(f"Total ATC Instructions: {status['total_instructions']}")
        print(f"Separation Violations: {status['violations']}")
        print(f"Near Misses: {status['near_misses']}")
        print(f"{'='*60}\n")
