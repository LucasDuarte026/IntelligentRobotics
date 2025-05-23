#!/usr/bin/env python3
import rospy
from std_msgs.msg import Float64
from pynput import keyboard
import threading
import time
import math

class CarKeyboardController:
    def __init__(self):
        rospy.init_node('car_keyboard_controller', anonymous=True)
        
        # Publishers for wheel effort controllers
        self.back_left_pub = rospy.Publisher('/car/back_left_wheel_effort_controller/command', Float64, queue_size=10)
        self.back_right_pub = rospy.Publisher('/car/back_right_wheel_effort_controller/command', Float64, queue_size=10)
        
        # Publishers for steering controllers
        self.steer_left_pub = rospy.Publisher('/car/front_left_wheel_effort_controller/command', Float64, queue_size=10)
        self.steer_right_pub = rospy.Publisher('/car/front_right_wheel_effort_controller/command', Float64, queue_size=10)

        # Parameters
        self.max_effort = 10.0
        self.effort_level = 3.0
        self.max_steering_angle = 0.785  # 45 degrees in radians
        self.steering_step = 0.005  # How much to change steering angle per update
        self.current_steering = 0.0  # Current steering angle (0 = straight)
        self.effort_change_amount = 0.3 # increases/decreases the power by this amount when +/- is pressed

        # Track key states
        self.keys_pressed = set()
        
        # Control loop rate (Hz)
        self.rate = 20
        
        # Display starting message
        self.display_controls()
    
    def display_controls(self):
        """Display control instructions to the user"""
        rospy.loginfo("=== Car Keyboard Controller ===")
        rospy.loginfo("Controls:")
        rospy.loginfo("  ↑     - Move forward")
        rospy.loginfo("  ↓     - Move backward")
        rospy.loginfo("  ←     - Turn left")
        rospy.loginfo("  →     - Turn right")
        rospy.loginfo("  +     - Increase power (current: %.1f)", self.effort_level)
        rospy.loginfo("  -     - Decrease power (current: %.1f)", self.effort_level)
        rospy.loginfo("  ESC   - Exit controller")
        rospy.loginfo("You can press multiple arrow keys simultaneously")
        
    def on_press(self, key):
        """Handle key press events"""
        try:
            # Add key to tracked keys if it's an arrow key or +/-
            if (key in [keyboard.Key.up, keyboard.Key.down, keyboard.Key.left, keyboard.Key.right] or 
                        (hasattr(key, 'char') and key.char in ['+', '-'])):
                self.keys_pressed.add(key)
                
                # Handle +/- immediately to adjust power
                if hasattr(key, 'char'):
                    if key.char == '+':
                        self.effort_level = min(self.max_effort, self.effort_level + self.effort_change_amount)
                        rospy.loginfo(f"Power increased to {self.effort_level:.1f}")
                    elif key.char == '-':
                        self.effort_level = max(self.effort_change_amount, self.effort_level - self.effort_change_amount)
                        rospy.loginfo(f"Power decreased to {self.effort_level:.1f}")
        except Exception as e:
            rospy.logerr(f"Error on key press: {e}")
    
    def on_release(self, key):
        """Handle key release events"""
        try:
            # Remove key from tracked keys
            if key in self.keys_pressed:
                self.keys_pressed.discard(key)
            
            # Handle ESC to exit
            if key == keyboard.Key.esc:
                rospy.loginfo("Exiting controller...")
                return False
        except Exception as e:
            rospy.logerr(f"Error on key release: {e}")
    
    def calculate_wheel_efforts(self):
        """Calculate wheel efforts based on pressed keys"""
        # Default: no movement
        left_effort = 0.0
        right_effort = 0.0
        
        # Determine forward/backward movement
        if keyboard.Key.up in self.keys_pressed:
            left_effort = right_effort = -self.effort_level
        elif keyboard.Key.down in self.keys_pressed:
            left_effort = right_effort = self.effort_level

        return left_effort, right_effort
    
    def update_steering(self):
        """Update steering angle based on pressed keys"""
        # Check if we should steer left or right
        if keyboard.Key.left in self.keys_pressed:
            self.current_steering = min(self.max_steering_angle, self.current_steering + self.steering_step)
        elif keyboard.Key.right in self.keys_pressed:
            self.current_steering = max(-self.max_steering_angle, self.current_steering - self.steering_step)
        else:
            #   Gradually return to center when no steering keys are pressed
             if abs(self.current_steering) > 0.01:
                 sign = 1 if self.current_steering > 0 else -1
                 self.current_steering = sign * max(0, abs(self.current_steering) - self.steering_step)
             else:
                 self.current_steering = 0.0
        
        # Publish steering commands (same angle for both wheels)
        self.steer_left_pub.publish(Float64(self.current_steering))
        self.steer_right_pub.publish(Float64(self.current_steering))
    
    def control_loop(self):
        """Main control loop that publishes wheel commands"""
        rate = rospy.Rate(self.rate)
        prev_left = prev_right = 0.0
        prev_steering = 0.0
        
        while not rospy.is_shutdown():
            # Calculate current wheel efforts
            left_effort, right_effort = self.calculate_wheel_efforts()
            
            # Update steering
            self.update_steering()
            
            # Only publish if values have changed
            if left_effort != prev_left or right_effort != prev_right:
                self.back_left_pub.publish(Float64(left_effort))
                self.back_right_pub.publish(Float64(right_effort))
                
                if left_effort == 0 and right_effort == 0:
                    rospy.loginfo("Stopping")
                else:
                    rospy.loginfo(f"Left wheel: {left_effort:.2f}, Right wheel: {right_effort:.2f}")
                
                prev_left, prev_right = left_effort, right_effort
            
            # Log steering changes if they're significant
            if abs(self.current_steering - prev_steering) > 0.01:
                degrees = math.degrees(self.current_steering)
                rospy.loginfo(f"Steering angle: {degrees:.1f}°")
                prev_steering = self.current_steering
            
            rate.sleep()
    
    def run(self):
        """Start the controller"""
        # Start keyboard listener in a non-blocking thread
        keyboard_listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        keyboard_listener.start()
        
        # Start control loop in a separate thread
        control_thread = threading.Thread(target=self.control_loop)
        control_thread.daemon = True
        control_thread.start()
        
        try:
            # Keep the main thread alive
            while keyboard_listener.is_alive() and not rospy.is_shutdown():
                time.sleep(0.1)
        except KeyboardInterrupt:
            rospy.loginfo("Interrupted by user")
        finally:
            # Stop wheels and center steering when shutting down
            self.back_left_pub.publish(Float64(0.0))
            self.back_right_pub.publish(Float64(0.0))
            self.steer_left_pub.publish(Float64(0.0))
            self.steer_right_pub.publish(Float64(0.0))
            keyboard_listener.stop()
            rospy.loginfo("Controller stopped")


if __name__ == '__main__':
    try:
        controller = CarKeyboardController()
        controller.run()
    except rospy.ROSInterruptException:
        pass