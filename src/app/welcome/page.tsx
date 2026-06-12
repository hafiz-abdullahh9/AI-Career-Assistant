"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Mail,
  Lock,
  User,
  Sparkles,
  ArrowRight,
  Briefcase,
  TrendingUp,
  Compass,
  CheckCircle,
} from "lucide-react";
import styles from "./Welcome.module.css";

export default function WelcomePage() {
  const router = useRouter();

  // Mode: 'signin' | 'signup'
  const [mode, setMode] = useState<"signin" | "signup">("signin");

  // Fields
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const handleAuthSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (mode === "signin") {
      // Mock Sign In
      if (!email || !password) {
        alert("Please enter both email and password.");
        return;
      }
      localStorage.setItem("isLoggedIn", "true");
      // If user was previously onboarded, go to dash, otherwise go to onboarding
      const isOnboarded = localStorage.getItem("isOnboarded");
      if (isOnboarded === "true") {
        router.push("/");
      } else {
        router.push("/onboarding");
      }
    } else {
      // Mock Sign Up
      if (!email || !password || !fullName || !confirmPassword) {
        alert("Please fill out all fields.");
        return;
      }
      if (password !== confirmPassword) {
        alert("Passwords do not match.");
        return;
      }
      localStorage.setItem("isLoggedIn", "true");
      localStorage.setItem("isOnboarded", "false");
      // Set user's name
      localStorage.setItem("userName", fullName);
      router.push("/onboarding");
    }

    // Force layout reload to update sidebar visibility
    window.dispatchEvent(new Event("storage"));
  };

  const handleGoogleAuth = () => {
    // Mock Google Sign-In
    localStorage.setItem("isLoggedIn", "true");
    localStorage.setItem("isOnboarded", "false");
    localStorage.setItem("userName", "Google User");
    router.push("/onboarding");

    // Force layout reload
    window.dispatchEvent(new Event("storage"));
  };

  const features = [
    {
      title: "Scrape & Verify Jobs",
      desc: "Autonomously collects listings from LinkedIn & Indeed, filtering duplicates and duplicate postings.",
      icon: Briefcase,
    },
    {
      title: "ATS Optimization & Cover Letters",
      desc: "Reorganizes and rephrases details on your CV for target matching without creating false info.",
      icon: Sparkles,
    },
    {
      title: "Automated Application Dispatch",
      desc: "Dispatches resumes via API emails and handles forms using browser automation.",
      icon: TrendingUp,
    },
    {
      title: "Skill Gap & Mock Interview Prep",
      desc: "Builds learning pathways and tests performance with speech-to-text live simulated interviews.",
      icon: Compass,
    },
  ];

  return (
    <div className={styles.container}>
      {/* Left Pane: Branding & Features */}
      <div className={styles.leftPane}>
        <div className={styles.logoArea}>
          <div className={styles.logoIcon}>
            <Sparkles size={22} />
          </div>
          <span>CareerFlow AI</span>
        </div>

        <h1 className={styles.headline}>
          Automate your job search. Land your next role.
        </h1>
        <p className={styles.tagline}>
          An intelligent multi-agent platform designed to automate and optimize the entire job application lifecycle — from matching to submission and mock interviews.
        </p>

        <div className={styles.featuresList}>
          {features.map((feat, idx) => {
            const Icon = feat.icon;
            return (
              <div key={idx} className={styles.featureItem}>
                <div className={styles.featureIcon}>
                  <Icon size={18} />
                </div>
                <div>
                  <h4 className={styles.featureTitle}>{feat.title}</h4>
                  <p className={styles.featureDesc}>{feat.desc}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Right Pane: Auth Card */}
      <div className={styles.rightPane}>
        <div className={`${styles.authCard} glass`}>
          <div className={styles.authHeader}>
            <h2 className={styles.authTitle}>
              {mode === "signin" ? "Welcome Back" : "Create Account"}
            </h2>
            <p className={styles.authSubtitle}>
              {mode === "signin"
                ? "Enter your credentials to manage your career agents"
                : "Sign up to start automated applications"}
            </p>
          </div>

          {/* Social Auth (Google OAuth) */}
          <button className={styles.googleBtn} onClick={handleGoogleAuth}>
            <svg className={styles.googleIcon} viewBox="0 0 24 24">
              <path
                fill="#EA4335"
                d="M12 5.04c1.64 0 3.12.56 4.28 1.67l3.2-3.2C17.52 1.58 14.94 1 12 1 7.24 1 3.2 3.73 1.24 7.72l3.78 2.93c.92-2.76 3.51-4.61 6.98-4.61z"
              />
              <path
                fill="#4285F4"
                d="M23.49 12.27c0-.81-.07-1.59-.2-2.34H12v4.44h6.45c-.28 1.48-1.12 2.74-2.38 3.59l3.7 2.87c2.16-2 3.72-4.94 3.72-8.56z"
              />
              <path
                fill="#FBBC05"
                d="M5.02 10.65c-.24-.72-.38-1.5-.38-2.3s.14-1.58.38-2.3L1.24 7.12C.45 8.71 0 10.49 0 12.35s.45 3.64 1.24 5.23l3.78-2.93z"
              />
              <path
                fill="#34A853"
                d="M12 23c3.24 0 5.97-1.07 7.96-2.92l-3.7-2.87c-1.03.69-2.35 1.1-4.26 1.1-3.47 0-6.06-1.85-6.98-4.61L1.24 16.63C3.2 20.62 7.24 23 12 23z"
              />
            </svg>
            <span>Continue with Google</span>
          </button>

          <div className={styles.divider}>or use email</div>

          {/* Core Credentials Form */}
          <form className={styles.form} onSubmit={handleAuthSubmit}>
            {mode === "signup" && (
              <div className={styles.inputGroup}>
                <label className={styles.inputLabel}>Full Name</label>
                <div className={styles.inputWrapper}>
                  <User size={16} className={styles.inputIcon} />
                  <input
                    type="text"
                    required
                    placeholder="Enter your name"
                    className={styles.inputField}
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                  />
                </div>
              </div>
            )}

            <div className={styles.inputGroup}>
              <label className={styles.inputLabel}>Email Address</label>
              <div className={styles.inputWrapper}>
                <Mail size={16} className={styles.inputIcon} />
                <input
                  type="email"
                  required
                  placeholder="name@example.com"
                  className={styles.inputField}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
            </div>

            <div className={styles.inputGroup}>
              <label className={styles.inputLabel}>Password</label>
              <div className={styles.inputWrapper}>
                <Lock size={16} className={styles.inputIcon} />
                <input
                  type="password"
                  required
                  placeholder="••••••••"
                  className={styles.inputField}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
            </div>

            {mode === "signup" && (
              <div className={styles.inputGroup}>
                <label className={styles.inputLabel}>Confirm Password</label>
                <div className={styles.inputWrapper}>
                  <Lock size={16} className={styles.inputIcon} />
                  <input
                    type="password"
                    required
                    placeholder="••••••••"
                    className={styles.inputField}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                  />
                </div>
              </div>
            )}

            {mode === "signin" && (
              <div className={styles.optionsRow}>
                <label className={styles.checkboxContainer}>
                  <input type="checkbox" style={{ transform: "scale(1.1)", cursor: "pointer" }} />
                  <span>Remember me</span>
                </label>
                <span className={styles.forgotLink} style={{ cursor: "pointer" }} onClick={() => alert("Mock Forgot Password clicked!")}>
                  Forgot Password?
                </span>
              </div>
            )}

            <button type="submit" className={styles.submitBtn}>
              <span>{mode === "signin" ? "Sign In" : "Sign Up & Start Onboarding"}</span>
            </button>
          </form>

          {/* Tab switches */}
          <div className={styles.switchMode}>
            {mode === "signin" ? (
              <span>
                Don&apos;t have an account?
                <span className={styles.switchLink} onClick={() => setMode("signup")}>
                  Sign Up
                </span>
              </span>
            ) : (
              <span>
                Already have an account?
                <span className={styles.switchLink} onClick={() => setMode("signin")}>
                  Sign In
                </span>
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
