"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  Briefcase,
  User,
  FileText,
  KanbanSquare,
  Compass,
  MessageSquareCode,
  LogOut,
  ChevronLeft,
  ChevronRight,
  Sparkles,
} from "lucide-react";
import styles from "./Sidebar.module.css";

interface SidebarProps {
  onCollapseToggle?: (isCollapsed: boolean) => void;
}

export default function Sidebar({ onCollapseToggle }: SidebarProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [userName, setUserName] = useState("John Doe");
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    // Dynamically retrieve name from local storage if set during sign up or onboarding
    const name = localStorage.getItem("userName");
    if (name) {
      setUserName(name);
    }
  }, [pathname]);

  const toggleSidebar = () => {
    const nextState = !isCollapsed;
    setIsCollapsed(nextState);
    if (onCollapseToggle) {
      onCollapseToggle(nextState);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("isLoggedIn");
    window.dispatchEvent(new Event("storage"));
    router.push("/welcome");
  };

  const navItems = [
    { label: "Dashboard", href: "/", icon: LayoutDashboard },
    { label: "Job Discovery", href: "/jobs", icon: Briefcase },
    { label: "CV & Profile", href: "/profile", icon: User },
    { label: "Document Hub", href: "/documents", icon: FileText },
    { label: "Application Tracker", href: "/tracker", icon: KanbanSquare },
    { label: "Career Roadmap", href: "/roadmap", icon: Compass },
    { label: "Interview Prep", href: "/interview", icon: MessageSquareCode },
  ];

  return (
    <>
      {/* Sidebar for Desktop */}
      <aside className={`${styles.sidebar} ${isCollapsed ? styles.collapsed : ""}`}>
        <div>
          <div className={styles.header}>
            <div className={styles.brand}>
              <div className={styles.logoIcon}>
                <Sparkles size={20} />
              </div>
              <span className={styles.brandLabel}>CareerFlow AI</span>
            </div>
            <button 
              className={styles.toggleBtn} 
              onClick={toggleSidebar}
              title={isCollapsed ? "Expand Sidebar" : "Collapse Sidebar"}
            >
              {isCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
            </button>
          </div>

          <nav className={styles.nav}>
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`${styles.navLink} ${isActive ? styles.activeLink : ""}`}
                >
                  <Icon className={styles.linkIcon} />
                  <span className={styles.linkLabel}>{item.label}</span>
                </Link>
              );
            })}
          </nav>
        </div>

        <div className={styles.footer}>
          <div className={styles.profileCard}>
            <div className={styles.profileAvatar}>
              {userName.split(" ").map((n) => n[0]).join("").substring(0, 2).toUpperCase()}
            </div>
            <div className={styles.profileInfo}>
              <span className={styles.profileName}>{userName}</span>
              <span className={styles.profileRole}>Candidate Profile</span>
            </div>
          </div>
          <button className={styles.logoutBtn} onClick={handleLogout}>
            <LogOut className={styles.linkIcon} />
            <span className={styles.linkLabel}>Log Out</span>
          </button>
        </div>
      </aside>

      {/* Mobile Top Navigation */}
      <div className={styles.mobileNavbar}>
        <div className={styles.brand} style={{ opacity: 1 }}>
          <div className={styles.logoIcon} style={{ width: 32, height: 32 }}>
            <Sparkles size={16} />
          </div>
          <span style={{ fontSize: 18 }}>CareerFlow AI</span>
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <Link href="/profile" style={{ display: "flex", alignItems: "center" }}>
            <div className={styles.profileAvatar} style={{ width: 32, height: 32, fontSize: 12 }}>
              {userName.split(" ").map((n) => n[0]).join("").substring(0, 2).toUpperCase()}
            </div>
          </Link>
        </div>
      </div>
    </>
  );
}
