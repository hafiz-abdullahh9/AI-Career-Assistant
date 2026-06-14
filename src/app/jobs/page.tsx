"use client";

import React, { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  Search,
  MapPin,
  DollarSign,
  Briefcase,
  Sparkles,
  CheckCircle,
  AlertCircle,
  HelpCircle,
  FileText,
  Play,
  Check,
  ExternalLink,
  ChevronRight,
  TrendingUp,
} from "lucide-react";
import styles from "./Jobs.module.css";

interface Job {
  id: string;
  title: string;
  company: string;
  logo: string;
  match: number;
  location: string;
  salary: string;
  type: string;
  experience: string;
  posted: string;
  skillsHave: string[];
  skillsMissing: string[];
  description: string;
}

const mockJobs: Job[] = [
  {
    id: "job-1",
    title: "Senior React Developer",
    company: "Vercel",
    logo: "V",
    match: 98,
    location: "Remote (US)",
    salary: "$140,000 - $170,000",
    type: "Full-time",
    experience: "Senior",
    posted: "2 hours ago",
    skillsHave: ["React", "Next.js", "TypeScript", "CSS Modules", "Git", "REST APIs"],
    skillsMissing: ["Rspack"],
    description: "We are looking for a Senior React Developer to join our core framework team. You will work on optimizing Next.js rendering, building highly interactive developer consoles, and improving bundle performance. The ideal candidate has deep knowledge of React internals, server components, and modern frontend architectures.",
  },
  {
    id: "job-2",
    title: "Software Engineer - Frontend",
    company: "Stripe",
    logo: "S",
    match: 92,
    location: "Remote / NYC",
    salary: "$135,000 - $160,000",
    type: "Full-time",
    experience: "Mid-Senior",
    posted: "5 hours ago",
    skillsHave: ["React", "TypeScript", "REST APIs", "Git"],
    skillsMissing: ["TailwindCSS", "CSS Modules"],
    description: "Join the dashboard team at Stripe to build beautiful, highly accessible financial tools. You will implement robust frontend payment systems, manage complex state architectures, and ensure top-tier performance for millions of active merchants worldwide.",
  },
  {
    id: "job-3",
    title: "Frontend Engineer",
    company: "Supabase",
    logo: "S",
    match: 87,
    location: "Remote",
    salary: "$110,000 - $130,000",
    type: "Full-time",
    experience: "Mid-level",
    posted: "1 day ago",
    skillsHave: ["React", "TypeScript", "Git"],
    skillsMissing: ["Postgres", "TailwindCSS"],
    description: "Looking for a Frontend Engineer to help us build the best open-source Firebase alternative. You will collaborate on the dashboard console, manage database visualizer interfaces, and build high-quality web experiences.",
  },
  {
    id: "job-4",
    title: "React Developer Intern",
    company: "Airbnb",
    logo: "A",
    match: 75,
    location: "San Francisco, CA",
    salary: "$45 - $60 / hour",
    type: "Internship",
    experience: "Entry-level",
    posted: "3 days ago",
    skillsHave: ["React", "CSS Modules", "Git"],
    skillsMissing: ["TypeScript", "Next.js", "GraphQL"],
    description: "Join the Airbnb guest experience team as a summer intern. You will work directly on customer-facing React components, write unit tests, and collaborate with UX designers to craft magical booking flows.",
  },
];

function JobsContent() {
  const searchParams = useSearchParams();
  const initialJobId = searchParams.get("id");

  // State
  const [jobs, setJobs] = useState<Job[]>(mockJobs);
  const [selectedJob, setSelectedJob] = useState<Job>(
    mockJobs.find((j) => j.id === initialJobId) || mockJobs[0]
  );
  const [searchQuery, setSearchQuery] = useState("");
  const [expFilter, setExpFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");

  // Automation overlay simulation state
  const [isAutoApplying, setIsAutoApplying] = useState(false);
  const [automationStep, setAutomationStep] = useState(0);

  useEffect(() => {
    if (initialJobId) {
      const job = mockJobs.find((j) => j.id === initialJobId);
      if (job) setSelectedJob(job);
    }
  }, [initialJobId]);

  // Filter Jobs
  const filteredJobs = jobs.filter((job) => {
    const matchesSearch =
      job.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      job.company.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesExp = expFilter ? job.experience.toLowerCase() === expFilter.toLowerCase() : true;
    const matchesType = typeFilter ? job.type.toLowerCase() === typeFilter.toLowerCase() : true;
    return matchesSearch && matchesExp && matchesType;
  });

  // Simulated auto-application timeline triggers
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
  };

  const automationSteps = [
    { id: 1, label: "Navigating to job portal and establishing sessions..." },
    { id: 2, label: "Scanning application page and detecting form fields..." },
    { id: 3, label: "Filling out application fields with verified profile data..." },
    { id: 4, label: "Attaching customized resume and cover letter..." },
    { id: 5, label: "Submitting application and resolving verification gates..." },
    { id: 6, label: "Application successfully submitted! Receipt stored." },
  ];

  return (
    <div className={styles.container}>
      {/* Left Pane: Job List */}
      <div className={styles.listPane}>
        <div className="glass searchBar" style={{ padding: 16 }}>
          <div className={styles.searchInputs}>
            <Search size={18} style={{ color: "var(--text-secondary)" }} />
            <input
              type="text"
              placeholder="Search jobs or companies..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <div className={styles.filterRow}>
            <select
              className={styles.filterSelect}
              value={expFilter}
              onChange={(e) => setExpFilter(e.target.value)}
            >
              <option value="">Experience Level</option>
              <option value="Entry-level">Entry-level</option>
              <option value="Mid-level">Mid-level</option>
              <option value="Senior">Senior</option>
            </select>
            <select
              className={styles.filterSelect}
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
            >
              <option value="">Job Type</option>
              <option value="Full-time">Full-time</option>
              <option value="Internship">Internship</option>
            </select>
          </div>
        </div>

        <div className={styles.jobList}>
          {filteredJobs.length > 0 ? (
            filteredJobs.map((job) => (
              <div
                key={job.id}
                className={`${styles.jobItem} ${
                  selectedJob.id === job.id ? styles.jobItemActive : ""
                } glass glass-hover`}
                onClick={() => setSelectedJob(job)}
              >
                <div className={styles.jobItemHeader}>
                  <div>
                    <h3 className={styles.jobItemTitle}>{job.title}</h3>
                    <span className={styles.jobItemCompany}>{job.company}</span>
                  </div>
                  <span
                    className={styles.compatScoreLarge}
                    style={{
                      fontSize: 12,
                      padding: "2px 6px",
                      color: job.match >= 90 ? "var(--secondary)" : "var(--primary)",
                      borderColor: job.match >= 90 ? "var(--secondary)" : "var(--primary)",
                      background: job.match >= 90 ? "rgba(20, 184, 166, 0.05)" : "rgba(99, 102, 241, 0.05)",
                    }}
                  >
                    {job.match}% Match
                  </span>
                </div>
                <div className={styles.jobItemMeta}>
                  <span className={styles.jobItemLocSal}>
                    {job.location} • {job.salary}
                  </span>
                  <span style={{ fontSize: 10, color: "var(--text-muted)" }}>
                    {job.posted}
                  </span>
                </div>
              </div>
            ))
          ) : (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 12,
                padding: 40,
                color: "var(--text-secondary)",
              }}
            >
              <AlertCircle size={28} />
              <span>No matching jobs found.</span>
            </div>
          )}
        </div>
      </div>

      {/* Right Pane: Detailed View */}
      {selectedJob ? (
        <div className={styles.detailPane}>
          {/* Header Card */}
          <div className="glass detailHeader">
            <div className={styles.companySection}>
              <div className={styles.largeLogo}>{selectedJob.logo}</div>
              <div className={styles.titleMeta}>
                <h2>{selectedJob.title}</h2>
                <span style={{ color: "var(--text-secondary)", fontSize: 14 }}>
                  {selectedJob.company} • {selectedJob.location} • {selectedJob.type}
                </span>
                <span style={{ color: "var(--text-muted)", fontSize: 12 }}>
                  Salary: {selectedJob.salary} • Experience: {selectedJob.experience}
                </span>
              </div>
            </div>
            <div className={styles.actionButtons}>
              <Link href={`/documents?jobId=${selectedJob.id}`}>
                <button className={styles.secondaryBtn}>
                  <FileText size={16} />
                  <span>Customize Documents</span>
                </button>
              </Link>
              <button className={styles.primaryBtn} onClick={startAutoApply}>
                <Play size={16} fill="white" />
                <span>Apply Automatically</span>
              </button>
            </div>
          </div>

          {/* AI Compatibility Analysis */}
          <div className="glass compatibilitySection">
            <div className={styles.compatHeader}>
              <div className={styles.compatHeaderTitle}>
                <Sparkles size={18} style={{ color: "var(--accent)" }} />
                <span>Job Compatibility Analysis</span>
              </div>
              <span className={styles.compatScoreLarge}>{selectedJob.match}% Match Score</span>
            </div>

            <div className={styles.compatGrid}>
              <div className={styles.compatItem}>
                <span className={styles.compatItemLabel}>Skills Compatibility</span>
                <div className={styles.compatBarContainer}>
                  <div
                    className={styles.compatBar}
                    style={{
                      width: `${selectedJob.match - 3}%`,
                      background: "var(--secondary)",
                    }}
                  ></div>
                </div>
                <span className={styles.compatItemValue}>
                  <span>{(selectedJob.match - 3).toString()}%</span>
                  <span style={{ color: "var(--success)", fontSize: 11 }}>Strong</span>
                </span>
              </div>
              <div className={styles.compatItem}>
                <span className={styles.compatItemLabel}>Experience Alignment</span>
                <div className={styles.compatBarContainer}>
                  <div
                    className={styles.compatBar}
                    style={{ width: "95%", background: "var(--primary)" }}
                  ></div>
                </div>
                <span className={styles.compatItemValue}>
                  <span>95%</span>
                  <span style={{ color: "var(--success)", fontSize: 11 }}>Optimal</span>
                </span>
              </div>
              <div className={styles.compatItem}>
                <span className={styles.compatItemLabel}>Location Preference</span>
                <div className={styles.compatBarContainer}>
                  <div
                    className={styles.compatBar}
                    style={{ width: "100%", background: "var(--secondary)" }}
                  ></div>
                </div>
                <span className={styles.compatItemValue}>
                  <span>100%</span>
                  <span style={{ color: "var(--success)", fontSize: 11 }}>Remote Matches</span>
                </span>
              </div>
            </div>

            {/* Skills Breakdown */}
            <div className={styles.skillsComparison}>
              <div className={styles.skillsGroup}>
                <span className={styles.skillsGroupTitle}>
                  <CheckCircle size={14} style={{ color: "var(--success)" }} />
                  <span>Matching Skills ({selectedJob.skillsHave.length})</span>
                </span>
                <div className={styles.skillsList}>
                  {selectedJob.skillsHave.map((skill, idx) => (
                    <span key={idx} className={styles.skillTagMatch}>
                      {skill}
                    </span>
                  ))}
                </div>
              </div>

              <div className={styles.skillsGroup}>
                <span className={styles.skillsGroupTitle}>
                  <AlertCircle size={14} style={{ color: "var(--warning)" }} />
                  <span>Missing Skills ({selectedJob.skillsMissing.length})</span>
                </span>
                <div className={styles.skillsList}>
                  {selectedJob.skillsMissing.map((skill, idx) => (
                    <Link key={idx} href="/roadmap">
                      <span className={styles.skillTagMissingLink}>
                        <span>{skill}</span>
                        <ChevronRight size={12} />
                      </span>
                    </Link>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Description Section */}
          <div className="glass descSection">
            <h3>Detailed Job Description</h3>
            <div className={styles.descContent}>
              <p>{selectedJob.description}</p>
              <p><strong>Key Responsibilities:</strong></p>
              <ul>
                <li>Architect and build scalable web interfaces using Next.js and React.</li>
                <li>Write production-ready, highly clean TypeScript components.</li>
                <li>Collaborate with product designers and engineers to create seamless user journeys.</li>
                <li>Optimize performance for maximum speed, accessibility, and SEO.</li>
              </ul>
              <p><strong>Required Qualifications:</strong></p>
              <ul>
                <li>Bachelor's degree in Computer Science or equivalent experience.</li>
                <li>Expert knowledge of modern JavaScript (ES6+), React, and structural CSS.</li>
                <li>Familiarity with browser automation, scraping, or web performance metrics.</li>
              </ul>
            </div>
          </div>
        </div>
      ) : null}

      {/* Application Automation Overlay (Agent Simulation) */}
      {isAutoApplying && (
        <div className={styles.modalOverlay}>
          <div className={`${styles.modalContent} glass`}>
            <div className={styles.modalHeader}>
              <Sparkles size={24} style={{ color: "var(--primary)", animation: "blink 1.5s infinite" }} />
              <h3 className={styles.modalHeaderTitle}>Application Automation Agent</h3>
            </div>
            
            <p className={styles.modalDesc}>
              The AI automation agent is filling out forms and submitting your optimized documents for <strong>{selectedJob.title}</strong> at <strong>{selectedJob.company}</strong>.
            </p>

            <div className={styles.progressContainer}>
              {automationSteps.map((step) => {
                const isActive = automationStep === step.id;
                const isCompleted = automationStep > step.id;
                return (
                  <div key={step.id} className={styles.stepRow}>
                    <div
                      className={`${styles.stepIcon} ${
                        isActive ? styles.stepActive : ""
                      } ${isCompleted ? styles.stepCompleted : ""}`}
                    >
                      {isCompleted ? <Check size={12} /> : step.id}
                    </div>
                    <span
                      className={`${styles.stepLabel} ${
                        isActive ? styles.stepLabelActive : ""
                      } ${isCompleted ? styles.stepLabelCompleted : ""}`}
                    >
                      {step.label}
                    </span>
                  </div>
                );
              })}
            </div>

            <div className={styles.progressBarBack}>
              <div
                className={styles.progressBarFill}
                style={{
                  width: `${(Math.min(automationStep, 6) / 6) * 100}%`,
                }}
              ></div>
            </div>

            {automationStep === 6 && (
              <button className={styles.closeModalBtn} onClick={closeAutomation}>
                Return to Dashboard
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function JobsPage() {
  return (
    <Suspense fallback={
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh" }}>
        <div className="status-dot active" style={{ width: 24, height: 24 }}></div>
        <span style={{ marginLeft: 12, color: "var(--text-secondary)" }}>Loading Jobs Dashboard...</span>
      </div>
    }>
      <JobsContent />
    </Suspense>
  );
}
