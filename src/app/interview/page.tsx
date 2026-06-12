"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  MessageSquareCode,
  Sparkles,
  Video,
  Mic,
  MicOff,
  Send,
  Play,
  TrendingUp,
  Award,
  BookOpen,
  ArrowRight,
  RefreshCcw,
  CheckCircle,
  HelpCircle,
  ChevronRight,
  Volume2,
} from "lucide-react";
import styles from "./Interview.module.css";

interface QAFeedback {
  question: string;
  answer: string;
  score: number;
  strength: string;
  improvement: string;
}

export default function InterviewPage() {
  // Simulator modes: 'setup' | 'active' | 'feedback'
  const [mode, setMode] = useState<"setup" | "active" | "feedback">("setup");
  const [targetJob, setTargetJob] = useState("Vercel - Senior React Developer");

  // Active session states
  const [questionIndex, setQuestionIndex] = useState(0);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [candidateTranscript, setCandidateTranscript] = useState("");

  const [chatLog, setChatLog] = useState<{ sender: "ai" | "user"; text: string }[]>([
    {
      sender: "ai",
      text: "Welcome, John. Let's start with your technical background. In Next.js, what is the core difference between Static Rendering and Dynamic Rendering, and how do you force a route to be evaluated dynamically?",
    },
  ]);

  const questions = [
    "In Next.js, what is the core difference between Static Rendering and Dynamic Rendering, and how do you force a route to be evaluated dynamically?",
    "Excellent explanation. Next, how would you optimize bundle sizes in a Next.js application that relies on heavy third-party visualization libraries?",
  ];

  const simulatedAnswers = [
    "In Next.js, static rendering pre-renders routes at build time, making them extremely fast and cacheable. Dynamic rendering renders routes at request time, which is necessary when pages need user-specific data. To force dynamic rendering, we can export const dynamic = 'force-dynamic' or use dynamic functions like cookies() or headers() inside the component.",
    "To optimize bundle sizes, I would use dynamic imports via next/dynamic to lazy load the heavy charts so they are only downloaded on the client when needed. I would also run @next/bundle-analyzer to audit packages and prune unused dependencies, or configure tree-shaking in imports.",
  ];

  // Feedback data
  const evaluationScore = 86;
  const qaFeedbacks: QAFeedback[] = [
    {
      question: "In Next.js, what is the core difference between Static Rendering and Dynamic Rendering, and how do you force a route to be evaluated dynamically?",
      answer: "In Next.js, static rendering pre-renders routes at build time, making them extremely fast and cacheable. Dynamic rendering renders routes at request time...",
      score: 90,
      strength: "Accurately identified build-time vs. request-time differences and correctly named dynamic utility tokens like cookies() and headers().",
      improvement: "Consider expanding on how CDN edge caching behaves during incremental static regeneration (ISR) for static pages.",
    },
    {
      question: "How would you optimize bundle sizes in a Next.js application that relies on heavy third-party visualization libraries?",
      answer: "To optimize bundle sizes, I would use dynamic imports via next/dynamic to lazy load the heavy charts so they are only downloaded on the client...",
      score: 82,
      strength: "Good utilization of next/dynamic for dynamic chunk loading and referencing the bundle analyzer for bundle audits.",
      improvement: "Prune filler phrases such as 'basically' or 'like' from speech starts to sound more authoritative in technical panels.",
    },
  ];

  // Handlers
  const startInterview = () => {
    setMode("active");
    setQuestionIndex(0);
    setCandidateTranscript("");
    setChatLog([
      {
        sender: "ai",
        text: questions[0],
      },
    ]);
  };

  const handleStartSpeaking = () => {
    setIsSpeaking(true);
    // Simulate candidate speaking and speech-to-text typing out
    setTimeout(() => {
      setCandidateTranscript(simulatedAnswers[questionIndex]);
      setIsSpeaking(false);
    }, 2000);
  };

  const handleSubmitAnswer = () => {
    if (!candidateTranscript) {
      alert("Please record or write your answer first!");
      return;
    }

    // Add candidate answer to log
    const updatedLog = [...chatLog, { sender: "user" as const, text: candidateTranscript }];
    setChatLog(updatedLog);
    setCandidateTranscript("");

    // Advance question or finish
    if (questionIndex < questions.length - 1) {
      const nextQIdx = questionIndex + 1;
      setQuestionIndex(nextQIdx);
      setTimeout(() => {
        setChatLog((prev) => [...prev, { sender: "ai", text: questions[nextQIdx] }]);
      }, 1000);
    } else {
      // Complete interview and go to feedback
      setTimeout(() => {
        setMode("feedback");
      }, 1500);
    }
  };

  return (
    <div className={styles.container}>
      {/* Header */}
      <header className={styles.header}>
        <h1>AI Interview Prep Center</h1>
        <p>
          Practice for target roles with our interactive mock interviewer. Receive instant scores and suggestions on communication clarity.
        </p>
      </header>

      {/* Setup screen */}
      {mode === "setup" && (
        <div className={`${styles.setupCard} glass`}>
          <div className={styles.setupIcon}>
            <MessageSquareCode size={32} />
          </div>
          <h2 className={styles.setupTitle}>Configure Practice Session</h2>
          <p className={styles.setupDesc}>
            The AI Agent will generate a custom panel simulation based on the requirements of your target job. It conducts technical screening, logs transcripts, and evaluates performance.
          </p>

          <div className={styles.selectBox} style={{ textAlign: "left" }}>
            <span style={{ fontSize: 11, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
              SELECT TARGET POSITION
            </span>
            <select
              style={{ background: "transparent", color: "inherit", width: "100%", fontSize: 14, cursor: "pointer" }}
              value={targetJob}
              onChange={(e) => setTargetJob(e.target.value)}
            >
              <option value="Vercel - Senior React Developer">Vercel - Senior React Developer (98% Match)</option>
              <option value="Stripe - Software Engineer Frontend">Stripe - Software Engineer - Frontend (92% Match)</option>
              <option value="Supabase - Frontend Engineer">Supabase - Frontend Engineer (87% Match)</option>
            </select>
          </div>

          <button className={styles.startBtn} onClick={startInterview}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
              <Play size={16} fill="white" />
              <span>Launch Mock Interview Simulator</span>
            </div>
          </button>
        </div>
      )}

      {/* Active Simulator Screen */}
      {mode === "active" && (
        <div className={styles.portalGrid}>
          {/* Left panel: Simulated Video feeds */}
          <div className={`${styles.videoFeedCard} glass`}>
            <div className={styles.panelTitle}>
              <Video size={18} style={{ color: "var(--accent)" }} />
              <span>Interactive Simulator Feeds</span>
            </div>

            {/* Simulated Interviewer Camera */}
            <div className={styles.videoPlaceholder}>
              <div className={styles.speakingIndicator}>
                <span className="status-dot active"></span>
                <span>Interviewer: AI Agent (speaking)</span>
              </div>
              <div className={styles.waveContainer}>
                <div className={styles.waveBar}></div>
                <div className={styles.waveBar}></div>
                <div className={styles.waveBar}></div>
                <div className={styles.waveBar}></div>
                <div className={styles.waveBar}></div>
                <div className={styles.waveBar}></div>
                <div className={styles.waveBar}></div>
              </div>
              <span style={{ fontSize: 13, color: "var(--text-secondary)", fontWeight: 600, marginTop: 12 }}>
                AI Core Platform Interviewer
              </span>
            </div>

            {/* Controls */}
            <div className={styles.controlsRow}>
              <button
                className={`${styles.micBtn} ${isSpeaking ? styles.micBtnActive : ""}`}
                onClick={handleStartSpeaking}
              >
                {isSpeaking ? (
                  <>
                    <MicOff size={16} />
                    <span>Listening voice...</span>
                  </>
                ) : (
                  <>
                    <Mic size={16} />
                    <span>Simulate Speaking (Answer)</span>
                  </>
                )}
              </button>
              <button className={styles.submitBtn} onClick={handleSubmitAnswer}>
                <Send size={16} />
                <span>Submit Answer</span>
              </button>
            </div>

            {/* Live speech transcription text-area */}
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <span style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700 }}>
                Live Speech-to-Text Transcription Output
              </span>
              <textarea
                className="glass"
                style={{
                  width: "100%",
                  minHeight: 80,
                  background: "rgba(255,255,255,0.02)",
                  border: "1px solid var(--border-color)",
                  borderRadius: 8,
                  padding: 12,
                  color: "var(--text-primary)",
                  fontSize: 13,
                  resize: "none",
                }}
                value={candidateTranscript}
                onChange={(e) => setCandidateTranscript(e.target.value)}
                placeholder="Click 'Simulate Speaking' or type your answer directly here..."
              />
            </div>
          </div>

          {/* Right Panel: Chat log feed */}
          <div className={`${styles.chatCard} glass`}>
            <div className={styles.panelTitle} style={{ borderBottom: "1px solid var(--border-color)", paddingBottom: 12 }}>
              <span>Live Interview Log</span>
            </div>

            <div style={{ display: "flex", flexDirection: "column", flex: 1, overflowY: "auto", gap: 16 }}>
              {chatLog.map((chat, idx) => (
                <div
                  key={idx}
                  className={`${styles.messageBubble} ${
                    chat.sender === "ai" ? styles.interviewerMsg : styles.candidateMsg
                  }`}
                >
                  <strong style={{ display: "block", fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>
                    {chat.sender === "ai" ? "AI INTERVIEWER" : "YOU (CANDIDATE)"}
                  </strong>
                  <span>{chat.text}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Feedback Review Screen */}
      {mode === "feedback" && (
        <div className={`${styles.feedbackCard} glass`}>
          <div className={styles.feedbackTitle}>
            <Award size={22} style={{ color: "var(--secondary)" }} />
            <span>AI Mock Performance Report</span>
          </div>

          {/* Overall grade and metrics */}
          <div className={styles.scoreRow}>
            <div className={styles.scoreCircle}>
              <span className={styles.scoreVal}>{evaluationScore}</span>
              <span className={styles.scoreLabel}>Score</span>
            </div>
            
            <div className={styles.sentimentCard}>
              <div>
                <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>Speech Pace</span>
                <div className={styles.sentimentVal}>122 WPM</div>
                <span style={{ fontSize: 9, color: "var(--success)" }}>Optimal</span>
              </div>
              <div>
                <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>Confidence Index</span>
                <div className={styles.sentimentVal}>High</div>
                <span style={{ fontSize: 9, color: "var(--success)" }}>Strong tone</span>
              </div>
              <div>
                <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>Grammar Rating</span>
                <div className={styles.sentimentVal}>Excellent</div>
                <span style={{ fontSize: 9, color: "var(--success)" }}>Few fillers</span>
              </div>
            </div>
          </div>

          {/* Question breakdown list */}
          <div className={styles.analysisSection}>
            <h3 style={{ fontSize: 16, fontWeight: 700, color: "var(--text-primary)" }}>
              Detailed Question-by-Question Grading
            </h3>

            {qaFeedbacks.map((qa, idx) => (
              <div key={idx} className={styles.analysisQuestionBlock}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <span style={{ fontSize: 13, fontWeight: 700, color: "var(--primary)" }}>
                    Question {idx + 1} ({qa.score}% Match Score)
                  </span>
                </div>
                <p style={{ fontSize: 13, color: "var(--text-primary)", fontWeight: 600, marginBottom: 6 }}>
                  Q: {qa.question}
                </p>
                <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12, fontStyle: "italic" }}>
                  Your Answer: &ldquo;{qa.answer}&rdquo;
                </p>

                <ul className={styles.bulletList}>
                  <li>
                    <strong style={{ color: "var(--success)" }}>Core Strength:</strong> {qa.strength}
                  </li>
                  <li>
                    <strong style={{ color: "var(--warning)" }}>Suggested Refinement:</strong> {qa.improvement}
                  </li>
                </ul>
              </div>
            ))}
          </div>

          {/* Action Footer */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderTop: "1px solid var(--border-color)", paddingTop: 20 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--text-secondary)" }}>
              <BookOpen size={16} />
              <span>We recommend practicing the Postgres components on your roadmap next.</span>
            </div>
            <div style={{ display: "flex", gap: 12 }}>
              <Link href="/roadmap">
                <button className={styles.submitBtn}>
                  <span>View Skills Roadmap</span>
                  <ChevronRight size={14} />
                </button>
              </Link>
              <button
                className={styles.startBtn}
                style={{ width: "auto", padding: "10px 20px" }}
                onClick={() => setMode("setup")}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <RefreshCcw size={14} />
                  <span>Practice Again</span>
                </div>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
