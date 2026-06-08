from manim import *

class CombustionEngine(Scene):
    def construct(self):
        # --- Setup cylinder and piston ---
        cylinder = Rectangle(height=5, width=2.5).shift(DOWN * 0.5)
        piston = Rectangle(height=0.6, width=2.3, fill_color=GREY, fill_opacity=1).move_to(DOWN * 1.8)

        # --- Labels ---
        title = Text("4-Stroke Combustion Engine", font_size=36).to_edge(UP)
        stroke_label = Text("", font_size=28).next_to(cylinder, RIGHT, buff=1.0)

        # --- Crankshaft circle (simplified representation) ---
        crankshaft = Circle(radius=0.3, color=WHITE).next_to(piston, DOWN, buff=0.5)
        connecting_rod = Line(piston.get_bottom(), crankshaft.get_top())

        # --- Add all components ---
        self.add(title, cylinder, piston, crankshaft, connecting_rod, stroke_label)

        # --- Function to move piston and update connecting rod ---
        def move_piston(y_target, duration=1.0):
            # Move the piston
            self.play(piston.animate.move_to([0, y_target, 0]), run_time=duration)
            # Instantly update connecting rod without animation
            connecting_rod.become(Line(piston.get_bottom(), crankshaft.get_top()))

        # --- Stroke 1: Intake ---
        stroke_label.become(Text("Intake Stroke", font_size=28, color=BLUE).next_to(cylinder, RIGHT, buff=1.0))
        intake_valve = Line([0.6, 2, 0], [0.6, 1.5, 0], color=BLUE)
        self.play(FadeIn(intake_valve))
        move_piston(-2.0)  # piston down
        self.play(FadeOut(intake_valve))

        # --- Stroke 2: Compression ---
        stroke_label.become(Text("Compression Stroke", font_size=28, color=YELLOW).next_to(cylinder, RIGHT, buff=1.0))
        move_piston(-1.0)  # piston up

        # --- Stroke 3: Power (Combustion) ---
        stroke_label.become(Text("Power Stroke", font_size=28, color=RED).next_to(cylinder, RIGHT, buff=1.0))
        flame = Circle(radius=0.3, color=ORANGE, fill_opacity=1).move_to([0, 1, 0])
        self.play(FadeIn(flame, scale=1.5), run_time=0.2)
        move_piston(-2.0, duration=0.7)  # piston pushed down
        self.play(FadeOut(flame))

        # --- Stroke 4: Exhaust ---
        stroke_label.become(Text("Exhaust Stroke", font_size=28, color=PURPLE).next_to(cylinder, RIGHT, buff=1.0))
        exhaust_valve = Line([-0.6, 2, 0], [-0.6, 1.5, 0], color=PURPLE)
        self.play(FadeIn(exhaust_valve))
        move_piston(-1.0)
        self.play(FadeOut(exhaust_valve))

        # --- Final Loop ---
        self.play(Indicate(stroke_label), run_time=0.5)
        self.wait(1)

