"use client";

import React, { useState, useEffect, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import {
  FileText,
  FileCode,
  Download,
  Play,
  Sparkles,
  Check,
  AlertTriangle,
  FileSpreadsheet,
  RefreshCw,
  Search,
} from "lucide-react";
import styles from "./Documents.module.css";
import jobsStyles from "../jobs/Jobs.module.css";

interface ResumeContent {
  name: string;
  contact: string;
  summary: string;
  experience: {
    role: string;
    company: string;
    duration: string;
    bullets: { text: string; isModified?: boolean; oldText?: string }[];
  }[];
  skills: string[];
}

const originalResume: ResumeContent = {
  name: "John Doe",
  contact: "john.doe@example.com • +92 300 1234567 • Karachi, Pakistan",
  summary: "Frontend developer with experience building web apps with React. Looking for my next challenge.",
  experience: [
    {
      role: "Frontend Developer",
      company: "TechCorp Solutions",
      duration: "June 2024 - Present",
      bullets: [
        { text: "Built SaaS layouts using React and Next." },
        { text: "Helped write CSS classes and handled state management." },
        { text: "Worked with design templates to create UI components." },
      ],
    },
    {
      role: "Software Intern",
      company: "DevSoft Hub",
      duration: "Nov 2023 - May 2024",
      bullets: [
        { text: "Created simple web pages and connected backend integrations." },
        { text: "Wrote frontend unit test configurations." },
      ],
    },
  ],
  skills: ["React", "JavaScript", "HTML", "CSS", "Git"],
};

const optimizedVercelResume: ResumeContent = {
  name: "John Doe",
  contact: "john.doe@example.com • +92 300 1234567 • Karachi, Pakistan (Open to Remote)",
  summary: "Results-driven Frontend Developer specializing in React and Next.js ecosystem. Adept at building production-ready architectures, optimizing server components, and styling with CSS modules.",
  experience: [
    {
      role: "Frontend Developer",
      company: "TechCorp Solutions",
      duration: "June 2024 - Present",
      bullets: [
        { text: "Architected scalable SaaS web interfaces using React, Next.js, and TypeScript, resulting in a 32% bundle size optimization.", isModified: true, oldText: "Built SaaS layouts using React and Next." },
        { text: "Engineered responsive layouts styled with Vanilla CSS Modules, ensuring modularity and eliminating CSS conflicts.", isModified: true, oldText: "Helped write CSS classes and handled state management." },
        { text: "Collaborated with product designers to implement pixel-perfect, highly accessible UI components complying with WCAG 2.1 AA guidelines.", isModified: true, oldText: "Worked with design templates to create UI components." },
      ],
    },
    {
      role: "Software Intern",
      company: "DevSoft Hub",
      duration: "Nov 2023 - May 2024",
      bullets: [
        { text: "Integrated RESTful APIs utilizing custom React Hooks and structured asynchronous states for robust data delivery.", isModified: true, oldText: "Created simple web pages and connected backend integrations." },
        { text: "Orchestrated frontend unit testing suites using Jest and React Testing Library to ensure 85% coverage.", isModified: true, oldText: "Wrote frontend unit test configurations." },
      ],
    },
  ],
  skills: ["React", "Next.js", "TypeScript", "CSS Modules", "Git", "REST APIs", "JavaScript", "Jest"],
};

const defaultCoverLetter = `Dear Hiring Team,

I am writing to express my enthusiastic interest in the Frontend position. With over two years of experience designing modular interfaces, writing semantic components, and structuring styling architectures, I am eager to contribute to your company.

During my tenure at TechCorp Solutions, I specialized in Next.js and styled component hierarchies. I spearheaded efforts that reduced client bundle sizes by 32% and successfully implemented accessible layouts conforming to WCAG standards. My dedication to semantic CSS and typed components makes me a strong fit for your framework-focused teams.

I look forward to discussing how my experience in responsive interfaces and automated testing layouts can benefit your products.

Sincerely,
John Doe`;

function DocumentsContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const jobId = searchParams.get("jobId") || "job-1";

  // States
  const [activeTab, setActiveTab] = useState<"resume" | "letter">("resume");
  const [coverLetter, setCoverLetter] = useState(defaultCoverLetter);
  const [isSaved, setIsSaved] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  // Application Automation overlay states (shared)
  const [isAutoApplying, setIsAutoApplying] = useState(false);
  const [automationStep, setAutomationStep] = useState(0);

  const jobTitle = jobId === "job-2" ? "Software Engineer" : "Senior React Developer";
  const jobCompany = jobId === "job-2" ? "Stripe" : "Vercel";

  const handleDownload = () => {
    setIsExporting(true);
    setTimeout(() => {
      setIsExporting(false);
      alert("Customized document exported as PDF successfully!");
    }, 1500);
  };

  const saveCoverLetter = () => {
    setIsSaved(true);
    setTimeout(() => setIsSaved(false), 2000);
  };

  const startAutoApply = () => {
    setIsAutoApplying(true);
    setAutomationStep(1);

    const timers = [
      setTimeout(() => setAutomationStep(2), 1200),
      setTimeout(() => setAutomationStep(3), 2500),
      setTimeout(() => setAutomationStep(4), 3800),
      setTimeout(() => setAutomationStep(5), 5000),
      setTimeout(() => setAutomationStep(6), 6500),
    ];

    return () => timers.forEach(clearTimeout);
  };

  const closeAutomation = () => {
    setIsAutoApplying(false);
    setAutomationStep(0);
    router.push("/tracker");
  };

  const automationSteps = [
    { id: 1, label: "Establishing connection session to job portal..." },
    { id: 2, label: "Injecting ATS-compatible customized resume headers..." },
    { id: 3, label: "Autofilling application form with verified profile tokens..." },
    { id: 4, label: "Uploading generated PDF attachments..." },
    { id: 5, label: "Reviewing submission compliance rules..." },
    { id: 6, label: "Application successfully submitted! Recruiter alerted." },
  ];

  return (
    <div className={styles.container}>
      {/* Header bar */}
      <header className={styles.header}>
        <div className={styles.titleSection}>
          <h1 className="animate-fade-in">AI Optimization Center</h1>
          <p>
            Reviewing customized documents optimized for: <strong>{jobTitle}</strong> at <strong>{jobCompany}</strong>
          </p>
        </div>
        <div className={styles.headerActions}>
          <button className={styles.secondaryBtn} onClick={handleDownload} disabled={isExporting}>
            <Download size={16} />
            <span>{isExporting ? "Exporting PDF..." : "Download PDF"}</span>
          </button>
          <button className={styles.primaryBtn} onClick={startAutoApply}>
            <Play size={16} fill="white" />
            <span>Apply Automatically</span>
          </button>
        </div>
      </header>

      {/* Info notice banner */}
      <div
        className="glass"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "12px 18px",
          background: "rgba(99, 102, 241, 0.08)",
          borderColor: "rgba(99, 102, 241, 0.2)",
          borderRadius: 12,
          fontSize: 13,
          color: "var(--text-secondary)",
        }}
      >
        <AlertTriangle size={18} style={{ color: "var(--primary)" }} />
        <span>
          <strong>Ethical AI Guard:</strong> Resumes are optimized by highlighting and rephrasing your existing verified credentials to align with ATS filters. <strong>No fictional skills or achievements have been generated.</strong>
        </span>
      </div>

      {/* Tabs */}
      <div className={styles.tabRow}>
        <button
          className={`${styles.tabBtn} ${activeTab === "resume" ? styles.tabBtnActive : ""}`}
          onClick={() => setActiveTab("resume")}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <FileCode size={16} />
            <span>ATS Resume Comparison</span>
          </div>
        </button>
        <button
          className={`${styles.tabBtn} ${activeTab === "letter" ? styles.tabBtnActive : ""}`}
          onClick={() => setActiveTab("letter")}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <FileText size={16} />
            <span>AI Cover Letter Editor</span>
          </div>
        </button>
      </div>

      {/* Content panes */}
      {activeTab === "resume" ? (
        <div className={styles.compareLayout}>
          {/* Original Resume Sheet */}
          <div className="glass cvPanel">
            <div className={styles.panelHeader}>
              <span className={styles.panelTitle}>Original CV</span>
              <span className={`${styles.badge} ${styles.originalBadge}`}>Unoptimized</span>
            </div>
            <div className={styles.resumeSheet}>
              <h3 className={styles.resumeTitle}>{originalResume.name}</h3>
              <p className={styles.resumeMeta}>{originalResume.contact}</p>

              <h4 className={styles.resumeSectionTitle}>Summary</h4>
              <p style={{ fontSize: 12, lineHeight: 1.6, marginBottom: 16 }}>{originalResume.summary}</p>

              <h4 className={styles.resumeSectionTitle}>Work Experience</h4>
              {originalResume.experience.map((exp, idx) => (
                <div key={idx} className={styles.resumeSection}>
                  <div className={styles.resumeItemTitle}>
                    <span>{exp.role}</span>
                    <span>{exp.duration}</span>
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 6 }}>{exp.company}</div>
                  <ul className={styles.resumeBullets}>
                    {exp.bullets.map((bullet, i) => (
                      <li key={i}>{bullet.text}</li>
                    ))}
                  </ul>
                </div>
              ))}

              <h4 className={styles.resumeSectionTitle}>Skills</h4>
              <p style={{ fontSize: 12 }}>{originalResume.skills.join(", ")}</p>
            </div>
          </div>

          {/* Optimized Resume Sheet */}
          <div className="glass cvPanel">
            <div className={styles.panelHeader}>
              <span className={styles.panelTitle}>
                <Sparkles size={16} style={{ color: "var(--secondary)" }} />
                <span>Optimized Resume (ATS Matches)</span>
              </span>
              <span className={`${styles.badge} ${styles.optimizedBadge}`}>95% ATS Compatibility</span>
            </div>
            <div className={styles.resumeSheet}>
              <h3 className={styles.resumeTitle}>{optimizedVercelResume.name}</h3>
              <p className={styles.resumeMeta}>{optimizedVercelResume.contact}</p>

              <h4 className={styles.resumeSectionTitle}>Summary</h4>
              <p style={{ fontSize: 12, lineHeight: 1.6, marginBottom: 16 }} className={styles.diffAdded}>
                {optimizedVercelResume.summary}
              </p>

              <h4 className={styles.resumeSectionTitle}>Work Experience</h4>
              {optimizedVercelResume.experience.map((exp, idx) => (
                <div key={idx} className={styles.resumeSection}>
                  <div className={styles.resumeItemTitle}>
                    <span>{exp.role}</span>
                    <span>{exp.duration}</span>
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 6 }}>{exp.company}</div>
                  <ul className={styles.resumeBullets}>
                    {exp.bullets.map((bullet, i) => (
                      <li key={i} className={bullet.isModified ? styles.diffAdded : ""}>
                        {bullet.isModified && (
                          <div className={styles.diffRemoved} style={{ marginBottom: 2 }}>
                            Was: {bullet.oldText}
                          </div>
                        )}
                        {bullet.text}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}

              <h4 className={styles.resumeSectionTitle}>Skills</h4>
              <p style={{ fontSize: 12 }} className={styles.diffAdded}>
                {optimizedVercelResume.skills.join(", ")}
              </p>
            </div>
          </div>
        </div>
      ) : (
        <div className={`${styles.coverLetterCard} glass`}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>
              <Sparkles size={16} style={{ color: "var(--secondary)" }} />
              <span>Tailored Cover Letter</span>
            </span>
            <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
              Addressed to {jobCompany} Hiring Team
            </span>
          </div>
          <textarea
            className={styles.coverLetterEditor}
            value={coverLetter}
            onChange={(e) => setCoverLetter(e.target.value)}
          />
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
              Cover letter automatically adapted using your profile achievements and Vercel job metrics.
            </span>
            <button className={styles.saveCoverLetterBtn} onClick={saveCoverLetter}>
              {isSaved ? (
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Check size={16} />
                  <span>Letter Saved</span>
                </div>
              ) : (
                "Save Cover Letter"
              )}
            </button>
          </div>
        </div>
      )}

      {/* Shared Application Automation Overlay */}
      {isAutoApplying && (
        <div className={jobsStyles.modalOverlay}>
          <div className={`${jobsStyles.modalContent} glass`}>
            <div className={jobsStyles.modalHeader}>
              <Sparkles size={24} style={{ color: "var(--primary)", animation: "blink 1.5s infinite" }} />
              <h3 className={jobsStyles.modalHeaderTitle}>Application Automation Agent</h3>
            </div>

            <p className={jobsStyles.modalDesc}>
              Submitting optimized PDF document and personalized cover letter to <strong>{jobCompany}</strong> for the <strong>{jobTitle}</strong> opening.
            </p>

            <div className={jobsStyles.progressContainer}>
              {automationSteps.map((step) => {
                const isActive = automationStep === step.id;
                const isCompleted = automationStep > step.id;
                return (
                  <div key={step.id} className={jobsStyles.stepRow}>
                    <div
                      className={`${jobsStyles.stepIcon} ${
                        isActive ? jobsStyles.stepActive : ""
                      } ${isCompleted ? jobsStyles.stepCompleted : ""}`}
                    >
                      {isCompleted ? <Check size={12} /> : step.id}
                    </div>
                    <span
                      className={`${jobsStyles.stepLabel} ${
                        isActive ? jobsStyles.stepLabelActive : ""
                      } ${isCompleted ? jobsStyles.stepLabelCompleted : ""}`}
                    >
                      {step.label}
                    </span>
                  </div>
                );
              })}
            </div>

            <div className={jobsStyles.progressBarBack}>
              <div
                className={jobsStyles.progressBarFill}
                style={{
                  width: `${(Math.min(automationStep, 6) / 6) * 100}%`,
                }}
              ></div>
            </div>

            {automationStep === 6 && (
              <button className={jobsStyles.closeModalBtn} onClick={closeAutomation}>
                View in Application Tracker
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function DocumentsPage() {
  return (
    <Suspense fallback={
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh" }}>
        <div className="status-dot active" style={{ width: 24, height: 24 }}></div>
        <span style={{ marginLeft: 12, color: "var(--text-secondary)" }}>Loading Document Customizer...</span>
      </div>
    }>
      <DocumentsContent />
    </Suspense>
  );
}
