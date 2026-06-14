"use client";

import React, { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  Sparkles,
  ArrowRight,
  ArrowLeft,
  UploadCloud,
  Check,
  Briefcase,
  MapPin,
  BookOpen,
  DollarSign,
  TrendingUp,
} from "lucide-react";
import styles from "./Onboarding.module.css";
import profileStyles from "../profile/Profile.module.css";

export default function OnboardingPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Wizard state (1 to 4)
  const [step, setStep] = useState(1);

  // Step 1: Background
  const [country, setCountry] = useState("Pakistan");
  const [targetJob, setTargetJob] = useState("Frontend Engineer");
  const [experienceLevel, setExperienceLevel] = useState("Entry-level");

  // Step 2: Resume Upload
  const [fileName, setFileName] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  // Step 3: Education & Goals
  const [degree, setDegree] = useState("Bachelor of Computer Science");
  const [institution, setInstitution] = useState("DHA Suffa University");
  const [careerGoals, setCareerGoals] = useState(
    "To specialize in React/Next.js frameworks and architect responsive, high-performance SaaS dashboards for global platforms."
  );

  // Step 4: Job Preferences
  const [prefRemote, setPrefRemote] = useState(true);
  const [prefHybrid, setPrefHybrid] = useState(true);
  const [prefOnsite, setPrefOnsite] = useState(false);
  const [minSalary, setMinSalary] = useState("120,000");
  const [maxSalary, setMaxSalary] = useState("150,000");

  // Resume Upload Handler
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setFileName(file.name);
      setIsUploading(true);
      setUploadProgress(0);

      // Simulate parsing
      const interval = setInterval(() => {
        setUploadProgress((prev) => {
          if (prev >= 100) {
            clearInterval(interval);
            setIsUploading(false);
            return 100;
          }
          return prev + 20;
        });
      }, 300);
    }
  };

  const nextStep = () => {
    // Basic validation
    if (step === 1 && !targetJob) {
      alert("Please enter a target job title.");
      return;
    }
    if (step === 2 && !fileName) {
      alert("Please upload your resume/CV to continue.");
      return;
    }
    if (step === 3 && (!degree || !institution)) {
      alert("Please complete your educational details.");
      return;
    }

    setStep(step + 1);
  };

  const prevStep = () => {
    setStep(step - 1);
  };

  const completeOnboarding = () => {
    // Save details to localStorage
    localStorage.setItem("isOnboarded", "true");
    localStorage.setItem("userCountry", country);
    localStorage.setItem("userJobTitle", targetJob);
    localStorage.setItem("userExperience", experienceLevel);
    localStorage.setItem("userDegree", degree);
    localStorage.setItem("userInstitution", institution);
    localStorage.setItem("userGoals", careerGoals);
    localStorage.setItem("userCvName", fileName);
    
    const prefs = [];
    if (prefRemote) prefs.push("Remote");
    if (prefHybrid) prefs.push("Hybrid");
    if (prefOnsite) prefs.push("On-site");
    localStorage.setItem("userWorkPrefs", prefs.join(", "));
    localStorage.setItem("userSalaryExpectation", `$${minSalary} - $${maxSalary}`);

    // Update userName if not set
    const currentName = localStorage.getItem("userName");
    if (!currentName || currentName === "Google User") {
      localStorage.setItem("userName", "John Doe");
    }

    // Redirect to Dashboard
    router.push("/");

    // Force layout reload to update sidebar status
    window.dispatchEvent(new Event("storage"));
  };

  return (
    <div className={styles.container}>
      {/* Questionnaire Form Card */}
      <div className={`${styles.onboardingCard} glass`}>
        {/* Header */}
        <header className={styles.header}>
          <h1>Agent Profile Setup</h1>
          <p>Configure your preferences so your AI Agents can customize resumes and find matching jobs.</p>
        </header>

        {/* Multi-step progress line */}
        <div className={styles.stepsIndicator}>
          <div 
            className={styles.indicatorLineActive} 
            style={{ width: `${((step - 1) / 3) * 100}%` }}
          ></div>
          <div className={`${styles.stepCircle} ${step >= 1 ? styles.stepActive : ""} ${step > 1 ? styles.stepCompleted : ""}`}>
            {step > 1 ? <Check size={14} /> : "1"}
          </div>
          <div className={`${styles.stepCircle} ${step >= 2 ? styles.stepActive : ""} ${step > 2 ? styles.stepCompleted : ""}`}>
            {step > 2 ? <Check size={14} /> : "2"}
          </div>
          <div className={`${styles.stepCircle} ${step >= 3 ? styles.stepActive : ""} ${step > 3 ? styles.stepCompleted : ""}`}>
            {step > 3 ? <Check size={14} /> : "3"}
          </div>
          <div className={`${styles.stepCircle} ${step >= 4 ? styles.stepActive : ""}`}>
            {step > 4 ? <Check size={14} /> : "4"}
          </div>
        </div>

        {/* Step 1: Background */}
        {step === 1 && (
          <div className={styles.formBody}>
            <h3 className={styles.formTitle}>Where should we start looking?</h3>
            
            <div className={styles.fieldGroup}>
              <label className={styles.fieldLabel}>Country of Residence</label>
              <select 
                className={styles.selectField}
                value={country}
                onChange={(e) => setCountry(e.target.value)}
              >
                <option value="Pakistan">Pakistan</option>
                <option value="United States">United States</option>
                <option value="United Kingdom">United Kingdom</option>
                <option value="United Arab Emirates">United Arab Emirates</option>
                <option value="Canada">Canada</option>
              </select>
            </div>

            <div className={styles.fieldGroup}>
              <label className={styles.fieldLabel}>Target Job Title</label>
              <input
                type="text"
                className={styles.inputField}
                placeholder="e.g. Frontend Engineer, React Developer"
                value={targetJob}
                onChange={(e) => setTargetJob(e.target.value)}
              />
            </div>

            <div className={styles.fieldGroup}>
              <label className={styles.fieldLabel}>Experience Level</label>
              <select 
                className={styles.selectField}
                value={experienceLevel}
                onChange={(e) => setExperienceLevel(e.target.value)}
              >
                <option value="Entry-level">Entry-level / Intern (0-1 years)</option>
                <option value="Mid-level">Mid-level (2-4 years)</option>
                <option value="Senior">Senior / Tech Lead (5+ years)</option>
              </select>
            </div>
          </div>
        )}

        {/* Step 2: Resume Upload */}
        {step === 2 && (
          <div className={styles.formBody}>
            <h3 className={styles.formTitle}>Upload your current CV / Resume</h3>
            <p style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: -12, lineHeight: 1.4 }}>
              Our parser agent will extract your skills, educational nodes, and work timeline to build your core matching credentials.
            </p>

            {!isUploading ? (
              <div 
                className={styles.onboardingUpload}
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  type="file"
                  ref={fileInputRef}
                  style={{ display: "none" }}
                  accept=".pdf,.docx,.txt"
                  onChange={handleFileSelect}
                />
                <div className={profileStyles.uploadIcon} style={{ margin: 0 }}>
                  <UploadCloud size={24} />
                </div>
                <div>
                  <span style={{ fontWeight: 600, fontSize: 14, display: "block" }}>
                    Select CV File (PDF / DOCX)
                  </span>
                  <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                    Drag & Drop also supported
                  </span>
                </div>
                {fileName && (
                  <div style={{ fontSize: 13, color: "var(--secondary)", fontWeight: 600, marginTop: 4 }}>
                    File Selected: {fileName}
                  </div>
                )}
              </div>
            ) : (
              <div className={profileStyles.progressCard} style={{ background: "rgba(255,255,255,0.02)", borderRadius: 12, border: "1px solid var(--border-color)" }}>
                <div className={profileStyles.progressHeader}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>Uploading & Parsing File...</span>
                  <span style={{ fontSize: 13, fontWeight: 700, color: "var(--primary)" }}>{uploadProgress}%</span>
                </div>
                <div className={profileStyles.barBack}>
                  <div className={profileStyles.barFill} style={{ width: `${uploadProgress}%` }}></div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Step 3: Education & Career Goals */}
        {step === 3 && (
          <div className={styles.formBody}>
            <h3 className={styles.formTitle}>Education & Career Vision</h3>

            <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16 }}>
              <div className={styles.fieldGroup}>
                <label className={styles.fieldLabel}>Degree / Major</label>
                <input
                  type="text"
                  className={styles.inputField}
                  value={degree}
                  onChange={(e) => setDegree(e.target.value)}
                />
              </div>
              <div className={styles.fieldGroup}>
                <label className={styles.fieldLabel}>Graduation</label>
                <input
                  type="text"
                  className={styles.inputField}
                  value={institution}
                  onChange={(e) => setInstitution(e.target.value)}
                  placeholder="e.g. 2025"
                />
              </div>
            </div>

            <div className={styles.fieldGroup}>
              <label className={styles.fieldLabel}>University / Institution</label>
              <input
                type="text"
                className={styles.inputField}
                value={institution}
                onChange={(e) => setInstitution(e.target.value)}
              />
            </div>

            <div className={styles.fieldGroup}>
              <label className={styles.fieldLabel}>Career Objectives</label>
              <textarea
                className={styles.textareaField}
                value={careerGoals}
                onChange={(e) => setCareerGoals(e.target.value)}
                placeholder="What is your immediate goal? e.g. Land a remote internship, transition to full-stack..."
              />
            </div>
          </div>
        )}

        {/* Step 4: Job Preferences */}
        {step === 4 && (
          <div className={styles.formBody}>
            <h3 className={styles.formTitle}>Job Search Preferences</h3>

            <div className={styles.fieldGroup}>
              <label className={styles.fieldLabel}>Work Settings</label>
              <div className={styles.checkboxGrid}>
                <div 
                  className={`${styles.checkboxCard} ${prefRemote ? styles.checkboxCardChecked : ""}`}
                  onClick={() => setPrefRemote(!prefRemote)}
                >
                  <input type="checkbox" checked={prefRemote} readOnly />
                  <span>Remote</span>
                </div>
                <div 
                  className={`${styles.checkboxCard} ${prefHybrid ? styles.checkboxCardChecked : ""}`}
                  onClick={() => setPrefHybrid(!prefHybrid)}
                >
                  <input type="checkbox" checked={prefHybrid} readOnly />
                  <span>Hybrid</span>
                </div>
                <div 
                  className={`${styles.checkboxCard} ${prefOnsite ? styles.checkboxCardChecked : ""}`}
                  onClick={() => setPrefOnsite(!prefOnsite)}
                >
                  <input type="checkbox" checked={prefOnsite} readOnly />
                  <span>On-site</span>
                </div>
              </div>
            </div>

            <div className={styles.fieldGroup}>
              <label className={styles.fieldLabel}>Salary Target Range (USD / Year)</label>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
                  <DollarSign size={16} style={{ position: "absolute", left: 12, color: "var(--text-muted)" }} />
                  <input
                    type="text"
                    className={styles.inputField}
                    style={{ paddingLeft: 32 }}
                    placeholder="Minimum e.g. 100,000"
                    value={minSalary}
                    onChange={(e) => setMinSalary(e.target.value)}
                  />
                </div>
                <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
                  <DollarSign size={16} style={{ position: "absolute", left: 12, color: "var(--text-muted)" }} />
                  <input
                    type="text"
                    className={styles.inputField}
                    style={{ paddingLeft: 32 }}
                    placeholder="Maximum e.g. 140,000"
                    value={maxSalary}
                    onChange={(e) => setMaxSalary(e.target.value)}
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Buttons footer */}
        <div className={styles.actionsRow}>
          {step > 1 ? (
            <button className={styles.backBtn} onClick={prevStep}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <ArrowLeft size={16} />
                <span>Back</span>
              </div>
            </button>
          ) : (
            <div></div> // Empty spacing
          )}

          {step < 4 ? (
            <button className={styles.nextBtn} onClick={nextStep}>
              <span>Continue</span>
              <ArrowRight size={16} />
            </button>
          ) : (
            <button className={styles.completeBtn} onClick={completeOnboarding}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Sparkles size={16} />
                <span>Complete Setup</span>
              </div>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
