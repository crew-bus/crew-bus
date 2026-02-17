"""
crew-bus Adaptive Instructor — Personalized teaching engine.

Generates lesson plans and adapts to the human's learning profile
in real-time. Uses the knowledge store and learning profile to
personalize every session.

Lesson plans are generated LOCALLY using templates and logic — no
external AI API calls. When users connect crew-bus to an AI model
(via OpenClaw or any other agent framework), the Ideas agent will
use this same structure but generate richer content through the AI.

FREE AND OPEN SOURCE — crew-bus is free infrastructure for the world.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
import bus


class Instructor:
    """Adaptive instruction engine.

    Generates lesson plans and adapts to the human's learning profile
    in real-time. Uses the knowledge store and learning profile to
    personalize every session.
    """

    def __init__(self, human_id: int, agent_id: int,
                 db_path: Optional[Path] = None):
        self.human_id = human_id
        self.agent_id = agent_id
        self.db_path = db_path

    def generate_lesson_plan(self, topic: str,
                             category: str = "general") -> list:
        """Generate a structured lesson plan for the topic.

        Considers the human's learning style, known skills, pace,
        detail level, and past sessions to build an appropriate plan.

        Returns a list of step dicts ready to insert into instruction_steps.
        """
        profile = bus.get_learning_profile(self.human_id, db_path=self.db_path)
        history = bus.get_instruction_history(self.human_id, limit=50,
                                             db_path=self.db_path)

        style = profile.get("learning_style", "adaptive")
        pace = profile.get("pace", "moderate")
        detail = profile.get("detail_level", "balanced")
        known = profile.get("known_skills", [])

        # Check if they've studied related topics before
        past_topics = [h["topic"].lower() for h in history]
        topic_lower = topic.lower()
        has_prior = any(t in topic_lower or topic_lower in t
                        for t in past_topics)

        # Determine step count based on pace
        if pace == "slow":
            base_steps = 7
        elif pace == "fast":
            base_steps = 4
        else:
            base_steps = 5

        # If they have prior knowledge, reduce intro steps
        if has_prior:
            base_steps = max(3, base_steps - 1)

        # Build the step sequence based on learning style
        steps = self._build_step_sequence(
            topic, category, style, detail, base_steps, known, has_prior)

        return steps

    def _build_step_sequence(self, topic: str, category: str,
                             style: str, detail: str,
                             num_steps: int, known: list,
                             has_prior: bool) -> list:
        """Build the actual step list based on style and category."""
        steps = []
        step_num = 1

        # Step 1: Introduction / Overview
        if not has_prior:
            steps.append({
                "step_number": step_num,
                "title": f"What is {topic}?",
                "content": self._gen_intro(topic, category, style, detail),
                "step_type": "explain",
            })
            step_num += 1

        # Step 2: Key Concepts
        steps.append({
            "step_number": step_num,
            "title": f"Core Concepts of {topic}",
            "content": self._gen_concepts(topic, category, style, detail,
                                          known),
            "step_type": "explain",
        })
        step_num += 1

        # Step 3: Demonstration or walkthrough
        steps.append({
            "step_number": step_num,
            "title": f"{topic} in Action",
            "content": self._gen_demo(topic, category, style, detail),
            "step_type": "demonstrate",
        })
        step_num += 1

        # Step 4: Practice (especially for kinesthetic learners)
        if style in ("kinesthetic", "adaptive") or num_steps >= 5:
            steps.append({
                "step_number": step_num,
                "title": f"Try It: {topic}",
                "content": self._gen_practice(topic, category, style, detail),
                "step_type": "practice",
            })
            step_num += 1

        # Step 5: Quiz / Knowledge check
        steps.append({
            "step_number": step_num,
            "title": f"Check Your Understanding",
            "content": self._gen_quiz(topic, category, style),
            "step_type": "quiz",
        })
        step_num += 1

        # Additional practice for slow pace
        if num_steps >= 6:
            steps.append({
                "step_number": step_num,
                "title": f"Advanced Practice: {topic}",
                "content": self._gen_advanced_practice(topic, category,
                                                      style, detail),
                "step_type": "practice",
            })
            step_num += 1

        # Additional detail step for slow pace
        if num_steps >= 7:
            steps.append({
                "step_number": step_num,
                "title": f"Deep Dive: {topic}",
                "content": self._gen_deep_dive(topic, category, style,
                                               detail),
                "step_type": "explain",
            })
            step_num += 1

        # Final checkpoint
        steps.append({
            "step_number": step_num,
            "title": "Session Checkpoint",
            "content": self._gen_checkpoint(topic),
            "step_type": "checkpoint",
        })

        return steps

    # ── Content generators ─────────────────────────────────────────

    def _gen_intro(self, topic: str, category: str, style: str,
                   detail: str) -> str:
        """Generate introduction content."""
        tone = self._tone_for_style(style)

        if detail == "just_steps":
            return (
                f"## {topic}\n\n"
                f"1. This session covers the fundamentals of {topic}\n"
                f"2. By the end, you'll understand the core concepts\n"
                f"3. You'll get hands-on practice\n"
            )

        if style == "visual":
            return (
                f"## {topic}\n\n"
                f"**Overview**\n\n"
                f"```\n"
                f"┌─────────────────────────┐\n"
                f"│       {topic[:20]:<20s} │\n"
                f"├─────────────────────────┤\n"
                f"│  What: Core skill/topic │\n"
                f"│  Why:  Practical value  │\n"
                f"│  How:  Step by step     │\n"
                f"└─────────────────────────┘\n"
                f"```\n\n"
                f"{topic} is a {self._category_label(category)} skill that "
                f"you'll find immediately useful. Let's break it down visually "
                f"so you can see how all the pieces connect.\n"
            )

        if style == "auditory":
            return (
                f"## Let's talk about {topic}\n\n"
                f"Think of it this way — {topic} is like learning to ride a "
                f"bike. At first it seems complicated, but once you get the "
                f"feel for it, it becomes second nature.\n\n"
                f"In this session, we'll walk through it together "
                f"conversationally. No jargon dumps — just plain talk about "
                f"what {topic} is and why it matters in the "
                f"{self._category_label(category)} world.\n"
            )

        if style == "kinesthetic":
            return (
                f"## {topic} — Hands-On Start\n\n"
                f"We're going to learn by doing. Instead of a long "
                f"explanation, let's jump in.\n\n"
                f"**What you'll need:**\n"
                f"- A willingness to experiment\n"
                f"- About 15-20 minutes of focus\n"
                f"- Don't worry about mistakes — that's how you learn\n\n"
                f"By the end of this session, you'll have actually *done* "
                f"something with {topic}, not just read about it.\n"
            )

        # reading / adaptive (default)
        return (
            f"## Introduction to {topic}\n\n"
            f"{topic} is a {self._category_label(category)} topic that "
            f"builds on fundamental concepts. This session will give you "
            f"a solid grounding in the essentials.\n\n"
            f"**What you'll learn:**\n"
            f"- The core principles of {topic}\n"
            f"- How to apply them in practice\n"
            f"- Common pitfalls to avoid\n"
        )

    def _gen_concepts(self, topic: str, category: str, style: str,
                      detail: str, known: list) -> str:
        """Generate core concepts content."""
        skip_note = ""
        if known:
            matching = [s for s in known
                        if s.lower() in topic.lower()
                        or topic.lower() in s.lower()]
            if matching:
                skip_note = (
                    f"\n> Since you already know **{', '.join(matching)}**, "
                    f"we'll skip the basics and focus on what's new.\n\n"
                )

        if style == "visual":
            return (
                f"## Key Concepts{skip_note}\n\n"
                f"```\n"
                f"  Concept 1          Concept 2          Concept 3\n"
                f"  ┌──────┐          ┌──────┐          ┌──────┐\n"
                f"  │ Core │ ──────── │Build │ ──────── │Apply │\n"
                f"  │ Idea │          │ On   │          │ It   │\n"
                f"  └──────┘          └──────┘          └──────┘\n"
                f"```\n\n"
                f"**Concept 1 — The Foundation:** Every {topic} journey "
                f"starts with understanding the basic building blocks.\n\n"
                f"**Concept 2 — Building Up:** Once you have the foundation, "
                f"you layer on more sophisticated techniques.\n\n"
                f"**Concept 3 — Application:** The real learning happens when "
                f"you apply these concepts to real situations.\n"
            )

        if detail == "concise" or detail == "just_steps":
            return (
                f"## Key Concepts{skip_note}\n\n"
                f"1. **Foundation** — The basics of {topic}\n"
                f"2. **Building blocks** — Core techniques and patterns\n"
                f"3. **Application** — Putting it together in practice\n"
            )

        return (
            f"## Key Concepts of {topic}{skip_note}\n\n"
            f"### 1. The Foundation\n"
            f"Every {self._category_label(category)} skill starts with "
            f"understanding the core principles. For {topic}, this means "
            f"grasping the fundamental ideas that everything else builds on.\n\n"
            f"### 2. Building Blocks\n"
            f"Once you understand the basics, you'll learn the key "
            f"techniques and patterns that practitioners use daily.\n\n"
            f"### 3. Practical Application\n"
            f"Knowledge without application is just trivia. We'll make sure "
            f"you can actually *use* what you're learning.\n"
        )

    def _gen_demo(self, topic: str, category: str, style: str,
                  detail: str) -> str:
        """Generate demonstration content."""
        if category == "tech":
            return (
                f"## {topic} — Demonstration\n\n"
                f"Here's how it works in practice:\n\n"
                f"```\n"
                f"Step 1: Set up your environment\n"
                f"Step 2: Follow the commands/process below\n"
                f"Step 3: Verify the result\n"
                f"```\n\n"
                f"**Walk-through:**\n\n"
                f"First, make sure you have the prerequisites. "
                f"Then follow along with each command or action. "
                f"Take your time — understanding is more important than speed.\n\n"
                f"**Expected result:** You should see the basic "
                f"functionality working. If something doesn't look right, "
                f"check the previous step.\n"
            )

        if category == "trades":
            return (
                f"## {topic} — Watch the Technique\n\n"
                f"**Safety first:**\n"
                f"- Wear appropriate protective equipment\n"
                f"- Work in a well-ventilated area\n"
                f"- Keep your workspace organized\n\n"
                f"**The technique:**\n\n"
                f"1. Prepare your materials and tools\n"
                f"2. Follow the proper form (described below)\n"
                f"3. Work slowly and deliberately\n"
                f"4. Check your work at each stage\n\n"
                f"**Key tip:** Speed comes with practice. Focus on "
                f"doing it right, not doing it fast.\n"
            )

        if category == "business":
            return (
                f"## {topic} — Real-World Example\n\n"
                f"**Scenario:**\n"
                f"Imagine you're applying {topic} in a real situation.\n\n"
                f"**Decision Framework:**\n\n"
                f"| Factor | Consider | Weight |\n"
                f"|--------|----------|--------|\n"
                f"| Cost   | Budget impact | High |\n"
                f"| Time   | Timeline pressure | Medium |\n"
                f"| Risk   | What could go wrong | High |\n"
                f"| ROI    | Expected return | High |\n\n"
                f"Walk through the framework with your specific situation "
                f"in mind. Each factor helps you make a better decision.\n"
            )

        # Generic
        return (
            f"## {topic} — See It in Action\n\n"
            f"Let's walk through a concrete example:\n\n"
            f"**Setup:** Start with the basic prerequisites\n\n"
            f"**Process:**\n"
            f"1. Begin with the foundational step\n"
            f"2. Apply the core technique\n"
            f"3. Observe the results\n"
            f"4. Adjust as needed\n\n"
            f"**What to look for:** Pay attention to how each step "
            f"connects to what you learned in the concepts section.\n"
        )

    def _gen_practice(self, topic: str, category: str, style: str,
                      detail: str) -> str:
        """Generate practice step content."""
        if category == "tech":
            return (
                f"## Your Turn: Practice {topic}\n\n"
                f"Now it's your turn to try. Here's your exercise:\n\n"
                f"**Exercise:**\n"
                f"Apply what you've learned about {topic} by completing "
                f"this task on your own.\n\n"
                f"**Steps:**\n"
                f"1. Set up a fresh starting point\n"
                f"2. Apply the technique from the demo\n"
                f"3. Verify your results match what you expect\n\n"
                f"**Hints:**\n"
                f"- If you get stuck, review the demonstration step\n"
                f"- It's okay to make mistakes — that's how you learn\n"
                f"- Try to do it without looking back first\n\n"
                f"When you're done, describe what you did and what "
                f"happened in the response box below.\n"
            )

        if category == "trades":
            return (
                f"## Hands-On: {topic}\n\n"
                f"**Your exercise:**\n\n"
                f"Using the technique from the demonstration, "
                f"complete this practice task.\n\n"
                f"**Checklist:**\n"
                f"- [ ] Safety equipment on\n"
                f"- [ ] Materials prepared\n"
                f"- [ ] Tools ready\n"
                f"- [ ] Workspace clear\n\n"
                f"Take your time. When you're done, rate how it went "
                f"and describe what you noticed.\n"
            )

        return (
            f"## Practice: {topic}\n\n"
            f"Time to put it into practice:\n\n"
            f"**Your task:** Apply {topic} concepts to a "
            f"real or hypothetical scenario.\n\n"
            f"Think about:\n"
            f"- What's the goal?\n"
            f"- What steps will you take?\n"
            f"- How will you know it worked?\n\n"
            f"Write your attempt or plan in the response box.\n"
        )

    def _gen_quiz(self, topic: str, category: str, style: str) -> str:
        """Generate quiz content."""
        return (
            f"## Quick Check: {topic}\n\n"
            f"Let's make sure the key ideas stuck.\n\n"
            f"**Question:** In your own words, explain the most important "
            f"concept you learned about {topic} and how you would apply it.\n\n"
            f"There's no wrong answer here — this is about checking your "
            f"own understanding. Be honest about what's clear and what's "
            f"still fuzzy.\n"
        )

    def _gen_advanced_practice(self, topic: str, category: str,
                               style: str, detail: str) -> str:
        """Generate advanced practice step."""
        return (
            f"## Level Up: {topic}\n\n"
            f"Now that you've got the basics down, let's push further.\n\n"
            f"**Advanced exercise:**\n"
            f"Take what you practiced and add a twist — try a more "
            f"complex scenario, combine it with something you already know, "
            f"or teach the concept to someone else (even if it's just "
            f"writing it out).\n\n"
            f"**The goal:** Move from \"I can follow instructions\" to "
            f"\"I understand this well enough to adapt it.\"\n\n"
            f"Describe what you tried and how it went.\n"
        )

    def _gen_deep_dive(self, topic: str, category: str, style: str,
                       detail: str) -> str:
        """Generate deep dive content for slow pace."""
        return (
            f"## Deep Dive: {topic}\n\n"
            f"Let's go deeper into the nuances.\n\n"
            f"**Common mistakes:**\n"
            f"- Rushing past the fundamentals\n"
            f"- Not practicing enough before moving on\n"
            f"- Trying to memorize instead of understanding\n\n"
            f"**Pro tips:**\n"
            f"- The best learners ask \"why?\" at every step\n"
            f"- Connect new knowledge to what you already know\n"
            f"- Review this material again tomorrow — spaced "
            f"repetition locks it in\n\n"
            f"**Further reading:**\n"
            f"Search for \"{topic} beginner guide\" or "
            f"\"{topic} tutorial\" to find more resources "
            f"that match your level.\n"
        )

    def _gen_checkpoint(self, topic: str) -> str:
        """Generate checkpoint content."""
        return (
            f"## Session Checkpoint\n\n"
            f"You've completed the lesson on **{topic}**.\n\n"
            f"Rate your confidence on a scale of 1-5:\n\n"
            f"- **1** — I'm lost, need to start over\n"
            f"- **2** — I get the basics but I'm shaky\n"
            f"- **3** — I understand it, but need more practice\n"
            f"- **4** — I'm comfortable and could do this on my own\n"
            f"- **5** — I could teach this to someone else\n\n"
            f"Be honest — your rating helps the system adapt to "
            f"teach you better next time.\n"
        )

    # ── Adaptation ─────────────────────────────────────────────────

    def adapt_next_step(self, session_id: int,
                        last_confidence: int) -> Optional[dict]:
        """Adjust remaining steps based on the human's last confidence score.

        If confidence was 1-2: insert an additional explanation step
        If confidence was 3: continue as planned
        If confidence was 4-5: skip the next explanation and go to practice/quiz

        Returns the newly inserted step dict, or None if no adaptation needed.
        """
        session = bus.get_instruction_session(session_id,
                                             db_path=self.db_path)
        if not session:
            return None

        steps = session.get("steps", [])
        completed_nums = [s["step_number"] for s in steps if s["completed"]]
        remaining = [s for s in steps if not s["completed"]]

        if not remaining:
            return None

        if last_confidence <= 2 and remaining:
            # Insert a remedial explanation before the next step
            next_step = remaining[0]
            new_num = next_step["step_number"]

            # Shift remaining steps up by 1
            conn = bus.get_conn(self.db_path)
            for s in remaining:
                conn.execute(
                    "UPDATE instruction_steps SET step_number = step_number + 1 "
                    "WHERE id=?", (s["id"],)
                )
            conn.commit()
            conn.close()

            # Insert the remedial step
            new_step = bus.add_instruction_step(
                session_id=session_id,
                step_number=new_num,
                title="Let's Review",
                content=(
                    f"## Let's slow down and review\n\n"
                    f"It seems like the last section was tricky. "
                    f"That's completely normal.\n\n"
                    f"**Key takeaway from the previous step:**\n"
                    f"Focus on understanding the *why*, not just the *how*.\n\n"
                    f"**Try this:** Explain what you've learned so far "
                    f"in your own words. Writing it out helps solidify "
                    f"your understanding.\n"
                ),
                step_type="explain",
                db_path=self.db_path,
            )
            return new_step

        if last_confidence >= 4 and len(remaining) >= 2:
            # Check if next step is an explanation we can skip
            next_step = remaining[0]
            if next_step["step_type"] == "explain":
                # Mark it completed automatically (skip it)
                bus.complete_instruction_step(
                    next_step["id"],
                    human_response="[Skipped — high confidence]",
                    confidence=last_confidence,
                    db_path=self.db_path,
                )
                return None

        return None

    def generate_step_content(self, topic: str, step_type: str,
                              context: dict) -> str:
        """Generate the content for a single step.

        This is where the actual teaching content is created.
        """
        style = context.get("learning_style", "adaptive")
        detail = context.get("detail_level", "balanced")
        category = context.get("category", "general")

        generators = {
            "explain": lambda: self._gen_concepts(topic, category, style,
                                                  detail, []),
            "demonstrate": lambda: self._gen_demo(topic, category, style,
                                                  detail),
            "practice": lambda: self._gen_practice(topic, category, style,
                                                   detail),
            "quiz": lambda: self._gen_quiz(topic, category, style),
            "checkpoint": lambda: self._gen_checkpoint(topic),
        }
        gen = generators.get(step_type, generators["explain"])
        return gen()

    def summarize_session(self, session_id: int) -> Optional[dict]:
        """Generate a summary of what was learned in the session.

        Stores key takeaways in the knowledge store so other agents
        can reference what the human knows.
        """
        session = bus.get_instruction_session(session_id,
                                             db_path=self.db_path)
        if not session:
            return None

        steps = session.get("steps", [])
        completed_steps = [s for s in steps if s["completed"]]
        confidences = [s["confidence"] for s in completed_steps
                       if s.get("confidence")]
        avg_confidence = (sum(confidences) / len(confidences)
                          if confidences else 0)

        summary = {
            "topic": session["topic"],
            "category": session["category"],
            "steps_completed": len(completed_steps),
            "steps_total": len(steps),
            "avg_confidence": round(avg_confidence, 1),
            "completed_at": session.get("completed_at"),
            "human_feedback": session.get("human_feedback"),
        }

        # Store in knowledge store
        bus.store_knowledge(
            agent_id=self.agent_id,
            category="lesson",
            subject=f"Completed lesson: {session['topic']}",
            content=summary,
            tags=f"instruction,{session['category']},{session['topic']}",
            db_path=self.db_path,
        )

        # If confidence is 4+, add to known_skills
        if avg_confidence >= 4.0:
            profile = bus.get_learning_profile(self.human_id,
                                              db_path=self.db_path)
            known = profile.get("known_skills", [])
            topic_lower = session["topic"].lower()
            if topic_lower not in [s.lower() for s in known]:
                known.append(session["topic"])
                bus.update_learning_profile(
                    self.human_id, {"known_skills": known},
                    db_path=self.db_path,
                )

        return summary

    # ── Helpers ────────────────────────────────────────────────────

    def _tone_for_style(self, style: str) -> str:
        tones = {
            "visual": "structured and diagram-heavy",
            "auditory": "conversational and story-driven",
            "reading": "detailed and reference-style",
            "kinesthetic": "action-oriented and hands-on",
            "adaptive": "balanced and clear",
        }
        return tones.get(style, "balanced and clear")

    def _category_label(self, category: str) -> str:
        labels = {
            "tech": "technology",
            "business": "business",
            "health": "health and wellness",
            "creative": "creative",
            "trades": "skilled trades",
            "life_skills": "life skills",
            "general": "general knowledge",
            "other": "general",
        }
        return labels.get(category, "general knowledge")
