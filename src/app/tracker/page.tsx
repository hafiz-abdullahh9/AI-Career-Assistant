"use client";

import React, { useState } from "react";
import {
  KanbanSquare,
  Sparkles,
  Search,
  Plus,
  X,
  Mail,
  Calendar,
  Clock,
  CheckCircle,
  AlertOctagon,
  StickyNote,
  UserCheck,
} from "lucide-react";
import styles from "./Tracker.module.css";

interface Application {
  id: string;
  title: string;
  company: string;
  logo: string;
  date: string;
  match: number;
  salary: string;
  status: "applied" | "review" | "interview" | "offer" | "rejected";
  method: "Email Automation" | "Web Form Fill";
  notes: string;
  emails: { sender: string; subject: string; date: string; content: string }[];
  history: { date: string; label: string }[];
}

const mockApplications: Application[] = [
  {
    id: "app-1",
    title: "Senior React Developer",
    company: "Vercel",
    logo: "V",
    date: "June 12, 2026",
    match: 98,
    salary: "$140k - $170k",
    status: "applied",
    method: "Email Automation",
    notes: "Reviewing panel scheduler. Practiced mock interview once. Need to focus on server components.",
    history: [
      { date: "June 12, 2026", label: "Optimized resume & cover letter generated." },
      { date: "June 12, 2026", label: "Email automation successfully dispatched application." },
    ],
    emails: [
      {
        sender: "Vercel Recruiting <jobs@vercel.com>",
        subject: "We received your application! - John Doe",
        date: "June 12, 2026 (2 hours ago)",
        content: "Hi John, thank you for applying to the Senior React Developer role! Our AI screening agent evaluated your profile at a 98% match rate. We will review your materials and follow up shortly.",
      },
    ],
  },
  {
    id: "app-2",
    title: "Software Engineer - Frontend",
    company: "Stripe",
    logo: "S",
    date: "June 11, 2026",
    match: 92,
    salary: "$135k - $160k",
    status: "review",
    method: "Web Form Fill",
    notes: "Applied using web form automation. Form fields mapped correctly.",
    history: [
      { date: "June 11, 2026", label: "Browser automation auto-filled Stripe portal." },
      { date: "June 11, 2026", label: "Status updated: Under Review." },
    ],
    emails: [
      {
        sender: "Stripe Careers <noreply@stripe.com>",
        subject: "Stripe application confirmation - John Doe",
        date: "June 11, 2026",
        content: "Hi John, your application is successfully registered in our dashboard. Our recruitment team is currently evaluating your profile relative to other applicants. We will reach out if we proceed.",
      },
    ],
  },
  {
    id: "app-3",
    title: "Frontend Engineer",
    company: "Supabase",
    logo: "S",
    date: "June 10, 2026",
    match: 87,
    salary: "$110k - $130k",
    status: "interview",
    method: "Web Form Fill",
    notes: "Mock interview scheduled. Will practice with AI Interview Simulator.",
    history: [
      { date: "June 10, 2026", label: "Submitted application via browser tool." },
      { date: "June 11, 2026", label: "Recruiter email received requesting interview." },
      { date: "June 12, 2026", label: "Mock preparation session scheduled." },
    ],
    emails: [
      {
        sender: "Supabase Hiring Team <hr@supabase.io>",
        subject: "Interview invitation: Supabase Frontend - John Doe",
        date: "June 11, 2026",
        content: "Hi John, we loved your optimized CV. We would like to invite you for a 45-minute technical screen next week. Please use the link below to select your preferred date...",
      },
    ],
  },
  {
    id: "app-4",
    title: "React Developer Intern",
    company: "Airbnb",
    logo: "A",
    date: "June 08, 2026",
    match: 75,
    salary: "$45 - $60 / hr",
    status: "applied",
    method: "Web Form Fill",
    notes: "No emails received yet.",
    history: [
      { date: "June 08, 2026", label: "Web form automated application sent." },
    ],
    emails: [],
  },
  {
    id: "app-5",
    title: "UI Engineer",
    company: "Spotify",
    logo: "S",
    date: "June 05, 2026",
    match: 81,
    salary: "$120k - $140k",
    status: "rejected",
    method: "Email Automation",
    notes: "Rejected due to lack of experience with Svelte/Vue. Need to upskill.",
    history: [
      { date: "June 05, 2026", label: "Application submitted via automated email." },
      { date: "June 09, 2026", label: "Rejection notification received." },
    ],
    emails: [
      {
        sender: "Spotify Recruiting <no-reply@spotify.com>",
        subject: "Spotify Application Update - UI Engineer",
        date: "June 09, 2026",
        content: "Hi John, thank you for applying. Unfortunately, we decided to move forward with candidates whose backgrounds align more closely with Svelte and component library design. We appreciate your time...",
      },
    ],
  },
];

const columns = [
  { id: "applied", title: "Applied", color: "var(--primary)" },
  { id: "review", title: "Under Review", color: "var(--secondary)" },
  { id: "interview", title: "Interviews", color: "var(--warning)" },
  { id: "offer", title: "Offers", color: "var(--success)" },
  { id: "rejected", title: "Rejected", color: "var(--danger)" },
];

export default function TrackerPage() {
  const [applications, setApplications] = useState<Application[]>(mockApplications);
  const [selectedApp, setSelectedApp] = useState<Application | null>(null);
  const [noteContent, setNoteContent] = useState("");

  const handleCardClick = (app: Application) => {
    setSelectedApp(app);
    setNoteContent(app.notes);
  };

  const handleSaveNotes = () => {
    if (selectedApp) {
      setApplications(
        applications.map((app) =>
          app.id === selectedApp.id ? { ...app, notes: noteContent } : app
        )
      );
      setSelectedApp({ ...selectedApp, notes: noteContent });
      alert("Notes updated successfully!");
    }
  };

  const getCount = (status: string) => {
    return applications.filter((app) => app.status === status).length;
  };

  return (
    <div className={styles.container}>
      {/* Page Header */}
      <header className={styles.header}>
        <h1>Application Tracking Dashboard</h1>
        <p>
          Track the status of all submitted applications. Status changes are automatically updated based on recruitment email patterns.
        </p>
      </header>

      {/* Kanban Board Grid */}
      <div className={styles.board}>
        {columns.map((col) => (
          <div key={col.id} className={`${styles.column} glass`}>
            <div className={styles.columnHeader} style={{ borderColor: col.color }}>
              <div className={styles.columnTitle}>
                <span className="status-dot" style={{ background: col.color, width: 8, height: 8 }}></span>
                <span>{col.title}</span>
              </div>
              <span className={styles.cardCount}>{getCount(col.id)}</span>
            </div>

            <div className={styles.cardsContainer}>
              {applications
                .filter((app) => app.status === col.id)
                .map((app) => (
                  <div
                    key={app.id}
                    className={`${styles.card} glass glass-hover`}
                    onClick={() => handleCardClick(app)}
                    style={{ background: "rgba(255,255,255,0.015)" }}
                  >
                    <div className={styles.cardHeader}>
                      <div>
                        <h4 className={styles.jobTitle}>{app.title}</h4>
                        <span className={styles.companyName}>{app.company}</span>
                      </div>
                      <span
                        className={styles.badge}
                        style={{
                          background: app.match >= 90 ? "rgba(20, 184, 166, 0.1)" : "rgba(99, 102, 241, 0.1)",
                          color: app.match >= 90 ? "var(--secondary)" : "var(--primary)",
                        }}
                      >
                        {app.match}%
                      </span>
                    </div>

                    <div className={styles.cardMeta}>
                      <span>{app.date}</span>
                      <span>{app.salary}</span>
                    </div>
                  </div>
                ))}

              {getCount(col.id) === 0 && (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    height: 100,
                    border: "1px dashed rgba(255, 255, 255, 0.04)",
                    borderRadius: 12,
                    fontSize: 11,
                    color: "var(--text-muted)",
                  }}
                >
                  No applications
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Card Detail Modal */}
      {selectedApp && (
        <div className={styles.modalOverlay}>
          <div className={`${styles.modalContent} glass`}>
            <div className={styles.modalHeader}>
              <div className={styles.modalTitleSection}>
                <h2>{selectedApp.title}</h2>
                <span style={{ color: "var(--text-secondary)", fontSize: 13 }}>
                  {selectedApp.company} • {selectedApp.salary} • Applied via {selectedApp.method}
                </span>
              </div>
              <button className={styles.closeModalBtn} onClick={() => setSelectedApp(null)}>
                <X size={20} />
              </button>
            </div>

            {/* Application Timeline */}
            <div>
              <h3 className={styles.columnTitle} style={{ marginBottom: 12 }}>
                <Clock size={16} style={{ color: "var(--primary)" }} />
                <span>Application Progress Timeline</span>
              </h3>
              <div className={styles.historyTimeline}>
                {selectedApp.history.map((hist, idx) => (
                  <div key={idx} className={styles.timelineItem}>
                    <div className={styles.timelineDot}></div>
                    <strong style={{ color: "var(--text-primary)" }}>{hist.date}</strong>: {hist.label}
                  </div>
                ))}
              </div>
            </div>

            {/* Email Interactions (Inbox Monitoring) */}
            <div>
              <h3 className={styles.columnTitle} style={{ marginBottom: 12 }}>
                <Mail size={16} style={{ color: "var(--secondary)" }} />
                <span>Recruiter Email Communications ({selectedApp.emails.length})</span>
              </h3>
              
              {selectedApp.emails.length > 0 ? (
                <div className={styles.emailThread}>
                  {selectedApp.emails.map((email, i) => (
                    <div key={i} className={styles.emailItem}>
                      <div className={styles.emailMeta}>
                        <strong>{email.sender}</strong>
                        <span>{email.date}</span>
                      </div>
                      <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)", marginBottom: 4 }}>
                        Subject: {email.subject}
                      </div>
                      <p className={styles.emailBody}>{email.content}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <div
                  style={{
                    padding: 16,
                    textAlign: "center",
                    fontSize: 12,
                    color: "var(--text-muted)",
                    background: "rgba(255,255,255,0.01)",
                    border: "1px solid var(--border-color)",
                    borderRadius: 8,
                  }}
                >
                  No communication threads detected. Inbox monitoring is active.
                </div>
              )}
            </div>

            {/* User Notes */}
            <div>
              <h3 className={styles.columnTitle} style={{ marginBottom: 12 }}>
                <StickyNote size={16} style={{ color: "var(--accent)" }} />
                <span>Interview Prep & Action Notes</span>
              </h3>
              <textarea
                className={styles.notesArea}
                value={noteContent}
                onChange={(e) => setNoteContent(e.target.value)}
                placeholder="Enter personal interview notes, questions to ask, or checklist tasks..."
              />
              <button
                className={styles.saveCoverLetterBtn}
                style={{ marginTop: 12 }}
                onClick={handleSaveNotes}
              >
                Save Notes
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
