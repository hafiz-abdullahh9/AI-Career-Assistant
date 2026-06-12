"use client";

import React, { useState } from "react";
import {
  Compass,
  Sparkles,
  TrendingUp,
  Award,
  BookOpen,
  CheckCircle,
  HelpCircle,
  Clock,
  ExternalLink,
  Lock,
  ArrowRight,
  Bookmark,
} from "lucide-react";
import styles from "./Roadmap.module.css";

interface SkillNode {
  id: string;
  name: string;
  status: "acquired" | "progress" | "locked";
  desc: string;
  roi: string;
  hours: number;
  course: string;
  platform: string;
  url: string;
}

const mockNodes: SkillNode[] = [
  {
    id: "node-1",
    name: "React & Next.js",
    status: "acquired",
    desc: "React Hooks, Context API, Next.js page structure, routing models, and server actions.",
    roi: "Verified Core Skill",
    hours: 0,
    course: "Completed TechCorp Onboarding",
    platform: "Internal",
    url: "#",
  },
  {
    id: "node-2",
    name: "Advanced TS",
    status: "acquired",
    desc: "Generics, utility types, conditional types, and TypeScript configurations in React projects.",
    roi: "Verified Core Skill",
    hours: 0,
    course: "Typescript Masterclass by Kent C.",
    platform: "Frontend Masters",
    url: "#",
  },
  {
    id: "node-3",
    name: "CSS Modules",
    status: "acquired",
    desc: "Vanilla CSS encapsulation, custom HSL styling systems, fluid typography, and transitions.",
    roi: "Verified Core Skill",
    hours: 0,
    course: "Modern CSS Architecture",
    platform: "Frontend Masters",
    url: "#",
  },
  {
    id: "node-4",
    name: "Postgres Database",
    status: "progress",
    desc: "Schema design, relational indexes, joins, triggers, and Supabase integration.",
    roi: "+$6,000 Market Value",
    hours: 15,
    course: "PostgreSQL & Supabase Mastery",
    platform: "Egghead.io",
    url: "https://egghead.io",
  },
  {
    id: "node-5",
    name: "Rspack Bundlers",
    status: "locked",
    desc: "Fast build compilers, configuring custom webpack overrides, bundle chunking.",
    roi: "+$5,000 Market Value",
    hours: 10,
    course: "Rspack & Webpack Deep Dive",
    platform: "Udemy",
    url: "https://udemy.com",
  },
  {
    id: "node-6",
    name: "GraphQL & APIs",
    status: "locked",
    desc: "Designing GraphQL schemas, mutations, Apollo Client cache strategies.",
    roi: "+$8,000 Market Value",
    hours: 18,
    course: "Apollo Client & GraphQL Fundamentals",
    platform: "Coursera",
    url: "https://coursera.org",
  },
];

export default function RoadmapPage() {
  const [selectedNode, setSelectedNode] = useState<SkillNode>(mockNodes[3]); // Default Postgres

  const missingSkills = mockNodes.filter((node) => node.status !== "acquired");

  return (
    <div className={styles.container}>
      {/* Page Header */}
      <header className={styles.header}>
        <h1>Skill Gap Analysis & Roadmap</h1>
        <p>
          AI-driven comparison between your current profile and matching criteria for target roles like <strong>Senior Web Architect</strong>.
        </p>
      </header>

      {/* Main Layout Grid */}
      <div className={styles.layout}>
        {/* Left Side: Roadmap Visualizer */}
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          <section className="glass panel">
            <div className={styles.panelTitle}>
              <Compass size={18} style={{ color: "var(--primary)" }} />
              <span>Target Role Roadmap: Lead React Architect</span>
            </div>

            <div className={styles.roadmapGraph}>
              {/* SVG Connector background */}
              <div className={styles.connectorLine}></div>

              <div className={styles.roadmapPath}>
                {mockNodes.map((node) => {
                  const isAcquired = node.status === "acquired";
                  const isProgress = node.status === "progress";
                  const isLocked = node.status === "locked";

                  return (
                    <div
                      key={node.id}
                      className={`${styles.node} ${
                        isAcquired ? styles.nodeAcquired : ""
                      } ${isProgress ? styles.nodeProgress : ""} ${
                        isLocked ? styles.nodeLocked : ""
                      }`}
                      onClick={() => setSelectedNode(node)}
                    >
                      <div className={styles.nodeIcon}>
                        {isAcquired && <CheckCircle size={16} />}
                        {isProgress && <TrendingUp size={16} />}
                        {isLocked && <Lock size={14} />}
                      </div>
                      <span className={styles.nodeLabel}>{node.name}</span>
                      <span className={styles.nodeStatus}>
                        {node.status === "acquired"
                          ? "Acquired"
                          : node.status === "progress"
                          ? "Learning"
                          : "Locked"}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Selected Node Details Box */}
            {selectedNode && (
              <div className={styles.nodeDetailsCard}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <h4 style={{ fontSize: 16, fontWeight: 700, color: "var(--text-primary)" }}>
                    {selectedNode.name}
                  </h4>
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: 700,
                      color: selectedNode.status === "acquired" ? "var(--success)" : "var(--warning)",
                    }}
                  >
                    {selectedNode.roi}
                  </span>
                </div>
                
                <p style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.5, marginBottom: 12 }}>
                  {selectedNode.desc}
                </p>

                {selectedNode.status !== "acquired" ? (
                  <div>
                    <span style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700, letterSpacing: 0.5 }}>
                      Recommended Resource
                    </span>
                    <a
                      href={selectedNode.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={styles.resourceLink}
                    >
                      <div>
                        <strong>{selectedNode.course}</strong>
                        <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2 }}>
                          {selectedNode.platform} • Est. Study Time: {selectedNode.hours} hrs
                        </div>
                      </div>
                      <ExternalLink size={14} />
                    </a>
                  </div>
                ) : (
                  <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--success)", fontWeight: 600 }}>
                    <CheckCircle size={14} />
                    <span>Skill verified via parsing and project audits.</span>
                  </div>
                )}
              </div>
            )}
          </section>

          {/* Table of priority gaps */}
          <section className="glass panel">
            <div className={styles.panelTitle}>
              <Award size={18} style={{ color: "var(--accent)" }} />
              <span>Prioritized Missing Skills Gaps</span>
            </div>

            <div className={styles.gapList}>
              {missingSkills.map((node) => (
                <div key={node.id} className={styles.gapItem}>
                  <div className={styles.gapInfo}>
                    <span className={styles.gapName}>{node.name}</span>
                    <span className={styles.gapMeta}>
                      Estimated study: <strong>{node.hours} hours</strong> • Course: {node.course} ({node.platform})
                    </span>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <span
                      className={`${styles.gapPriority} ${
                        node.id === "node-4" ? styles.priorityHigh : styles.priorityMedium
                      }`}
                    >
                      {node.id === "node-4" ? "High Priority" : "Medium Priority"}
                    </span>
                    <span style={{ fontSize: 12, fontWeight: 700, color: "var(--success)" }}>
                      {node.roi}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>

        {/* Right Side: Projections & Stats */}
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          {/* ROI summary */}
          <section className="glass panel" style={{ background: "linear-gradient(135deg, rgba(20, 184, 166, 0.08) 0%, rgba(99, 102, 241, 0.03) 100%)", borderColor: "rgba(20, 184, 166, 0.2)" }}>
            <div className={styles.panelTitle} style={{ marginBottom: 16 }}>
              <TrendingUp size={18} style={{ color: "var(--secondary)" }} />
              <span>Career Improvement Projections</span>
            </div>

            <div className={styles.projectionGrid}>
              <div className={styles.projCard}>
                <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>Market Salary Cap</span>
                <div className={styles.projVal}>+$19,000</div>
                <span style={{ fontSize: 9, color: "var(--text-muted)" }}>After roadmap completion</span>
              </div>
              <div className={styles.projCard}>
                <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>Recruiter Matches</span>
                <div className={styles.projVal}>+42%</div>
                <span style={{ fontSize: 9, color: "var(--text-muted)" }}>Profile search boost</span>
              </div>
            </div>

            <p style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.5, marginTop: 16, textAlign: "center" }}>
              Acquiring <strong>PostgreSQL</strong> unlocks <strong>8 additional recommended positions</strong> on Vercel and Stripe teams in your region.
            </p>
          </section>

          {/* Quick Study Checklist */}
          <section className="glass panel">
            <div className={styles.panelTitle} style={{ marginBottom: 16 }}>
              <BookOpen size={18} style={{ color: "var(--warning)" }} />
              <span>Learning Progress Checklist</span>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div style={{ display: "flex", gap: 12, fontSize: 13 }}>
                <input type="checkbox" defaultChecked disabled style={{ transform: "scale(1.1)", cursor: "not-allowed" }} />
                <span style={{ color: "var(--text-muted)", textDecoration: "line-through" }}>Configure types.d.ts settings in next.js</span>
              </div>
              <div style={{ display: "flex", gap: 12, fontSize: 13 }}>
                <input type="checkbox" defaultChecked disabled style={{ transform: "scale(1.1)", cursor: "not-allowed" }} />
                <span style={{ color: "var(--text-muted)", textDecoration: "line-through" }}>Optimize CSS Modules loading classes</span>
              </div>
              <div style={{ display: "flex", gap: 12, fontSize: 13 }}>
                <input type="checkbox" defaultChecked style={{ transform: "scale(1.1)" }} />
                <span>Complete Postgres Relational Joins tutorial module (Egghead)</span>
              </div>
              <div style={{ display: "flex", gap: 12, fontSize: 13 }}>
                <input type="checkbox" style={{ transform: "scale(1.1)" }} />
                <span>Build relational databases schema draft for Career Assistant API</span>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
