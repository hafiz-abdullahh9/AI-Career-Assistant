"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  Send,
  Sparkles,
  Briefcase,
  Calendar,
  TrendingUp,
  Brain,
  Zap,
  CheckCircle2,
  ArrowRight,
  ArrowUpRight,
  ShieldCheck,
  Code,
} from "lucide-react";
import styles from "./Dashboard.module.css";

export default function DashboardPage() {
  const [userName, setUserName] = useState("John");

  useEffect(() => {
    // Dynamic retrieval from local storage
    const name = localStorage.getItem("userName");
    if (name) {
      setUserName(name.split(" ")[0]);
    }
  }, []);

  const metrics = [
    {
      label: "Applications Sent",
      value: "42",
      trend: "+12% this week",
      trendDirection: "up",
      icon: Send,
      iconType: styles.primaryIcon,
    },
    {
      label: "Avg Match Rate",
      value: "87%",
      trend: "+4% from last profile update",
      trendDirection: "up",
      icon: Sparkles,
      iconType: styles.accentIcon,
    },
    {
      label: "Recommended Jobs",
      value: "18",
      trend: "5 high-compatibility",
      trendDirection: "neutral",
      icon: Briefcase,
      iconType: styles.secondaryIcon,
    },
    {
      label: "Interviews Booked",
      value: "3",
      trend: "Next: Monday 2:00 PM",
      trendDirection: "neutral",
      icon: Calendar,
      iconType: styles.warningIcon,
    },
  ];

  const topJobs = [
    {
      id: "job-1",
      title: "Senior React Developer",
      company: "Vercel",
      logo: "V",
      match: 98,
      location: "Remote (US)",
      salary: "$140k - $170k",
      tags: ["React", "Next.js", "TypeScript"],
    },
    {
      id: "job-2",
      title: "Software Engineer - frontend",
      company: "Stripe",
      logo: "S",
      match: 92,
      location: "Remote / NYC",
      salary: "$135k - $160k",
      tags: ["React", "CSS modules", "API Integration"],
    },
    {
      id: "job-3",
      title: "Frontend Engineer",
      company: "Supabase",
      logo: "S",
      match: 87,
      location: "Remote",
      salary: "$110k - $130k",
      tags: ["TypeScript", "Tailwind", "Postgres"],
    },
  ];

  const agentActivities = [
    {
      agent: "Job Scraping Agent",
      time: "2 hours ago",
      dotStyle: styles.secondary,
      title: "Scrape Complete",
      desc: "Scraped 142 new job listings matching search query parameters 'Frontend Developer' & 'React' from LinkedIn and Indeed.",
    },
    {
      agent: "Job Verification Agent",
      time: "2 hours ago",
      dotStyle: styles.accent,
      title: "Duplication & Legitimacy Check",
      desc: "Filtered 45 duplicates & 7 expired posts. Verified legitimacy of 97 companies using public records databases.",
    },
    {
      agent: "Resume Optimization Agent",
      time: "4 hours ago",
      dotStyle: styles.primary,
      title: "Resume Customization Done",
      desc: "Generated an optimized resume for 'Senior React Developer' at Vercel. ATS compatibility check score is 95%. No fictional facts added.",
    },
    {
      agent: "Application Automation Agent",
      time: "1 day ago",
      dotStyle: styles.success,
      title: "Auto-Submission Confirmed",
      desc: "Successfully submitted optimized resume and cover letter to Airbnb. Stored confirmation ID in Tracking Dashboard.",
    },
  ];

  return (
    <div className={styles.dashboardContainer}>
      {/* Welcome Section */}
      <header className={styles.welcomeSection}>
        <h1 className="animate-fade-in">Welcome Back, {userName}</h1>
        <p className={styles.welcomeSubtitle}>
          Your AI Agents are active. They have analyzed 142 job openings today and optimized 1 application.
        </p>
      </header>

      {/* Metrics Section */}
      <section className={styles.metricsGrid}>
        {metrics.map((m, idx) => {
          const Icon = m.icon;
          return (
            <div key={idx} className="glass glass-hover metric-card-animation" style={{ animationDelay: `${idx * 0.1}s` }}>
              <div className={styles.metricCard}>
                <div className={styles.metricContent}>
                  <span className={styles.metricLabel}>{m.label}</span>
                  <span className={styles.metricValue}>{m.value}</span>
                  <span className={styles.metricMeta}>
                    {m.trendDirection === "up" ? (
                      <TrendingUp size={12} className={styles.trendUp} />
                    ) : null}
                    <span style={{ color: m.trendDirection === "up" ? "var(--success)" : "var(--text-muted)" }}>
                      {m.trend}
                    </span>
                  </span>
                </div>
                <div className={`${styles.metricIconWrapper} ${m.iconType}`}>
                  <Icon size={20} />
                </div>
              </div>
            </div>
          );
        })}
      </section>

      {/* Main Grid Content */}
      <div className={styles.dashboardLayout}>
        {/* Left Side: Top Job Matches */}
        <section className="glass panel animate-slide-up" style={{ animationDelay: "0.2s" }}>
          <div className={styles.panelTitle}>
            <Brain size={18} style={{ color: "var(--primary)" }} />
            <span>AI Spotlight Recommendations</span>
          </div>
          
          <div className={styles.jobGrid}>
            {topJobs.map((job) => (
              <div key={job.id} className={`${styles.jobCard} glass-hover`} style={{ background: "rgba(255, 255, 255, 0.02)", border: "1px solid var(--border-color)", borderRadius: 12 }}>
                <div className={styles.jobInfo}>
                  <div className={styles.companyLogo}>{job.logo}</div>
                  <div className={styles.jobMeta}>
                    <span className={styles.jobTitle}>{job.title}</span>
                    <span className={styles.companyName}>
                      {job.company} • {job.location} • {job.salary}
                    </span>
                    <div className={styles.jobTags}>
                      {job.tags.map((t, i) => (
                        <span key={i} className={styles.tag}>
                          {t}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>

                <div className={styles.matchBadge}>
                  <div className={`${styles.scoreCircle} ${job.match >= 90 ? styles.high : ""}`}>
                    {job.match}%
                  </div>
                  <Link href={`/jobs?id=${job.id}`}>
                    <button className={styles.applyBtn}>
                      Optimize & Apply
                    </button>
                  </Link>
                </div>
              </div>
            ))}
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 20 }}>
            <Link href="/jobs" style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--primary)", fontWeight: 600 }}>
              <span>Browse All Recommended Jobs</span>
              <ArrowRight size={14} />
            </Link>
          </div>
        </section>

        {/* Right Side: Agent Activities & Actions */}
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {/* Quick Mock Interview Box */}
          <section className="glass panel animate-slide-up" style={{ animationDelay: "0.3s", padding: 20, background: "linear-gradient(135deg, rgba(99, 102, 241, 0.1) 0%, rgba(168, 85, 247, 0.05) 100%)", borderColor: "rgba(99, 102, 241, 0.2)" }}>
            <div className={styles.panelTitle} style={{ marginBottom: 12 }}>
              <Zap size={18} style={{ color: "var(--accent)" }} />
              <span>Next Action Required</span>
            </div>
            <p style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.5, marginBottom: 16 }}>
              You have a mock interview scheduled for <strong>Senior React Developer</strong> role at Vercel. Try a 10-minute prep session.
            </p>
            <Link href="/interview">
              <button 
                className={styles.applyBtn} 
                style={{ 
                  background: "linear-gradient(135deg, var(--primary) 0%, var(--accent) 100%)", 
                  width: "100%", 
                  display: "flex", 
                  alignItems: "center", 
                  justifyContent: "center", 
                  gap: 8,
                  padding: "10px 16px"
                }}
              >
                <span>Start Mock Interview</span>
                <ArrowUpRight size={14} />
              </button>
            </Link>
          </section>

          {/* Agent Activity Timeline */}
          <section className="glass panel animate-slide-up" style={{ animationDelay: "0.4s", padding: 20 }}>
            <div className={styles.panelTitle} style={{ marginBottom: 16 }}>
              <ShieldCheck size={18} style={{ color: "var(--secondary)" }} />
              <span>Multi-Agent Activity Log</span>
            </div>
            
            <div className={styles.timeline}>
              {agentActivities.map((act, i) => (
                <div key={i} className={styles.timelineItem}>
                  <div className={`${styles.timelineDot} ${act.dotStyle}`}></div>
                  <div className={styles.timelineTime}>{act.time}</div>
                  <div className={styles.timelineTitle}>{act.agent}</div>
                  <div className={`${styles.timelineDesc} ${styles.timelineCard}`}>
                    <strong>{act.title}</strong>: {act.desc}
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
