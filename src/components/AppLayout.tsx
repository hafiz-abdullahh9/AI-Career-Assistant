"use client";

import React, { useState, useEffect } from "react";
import Sidebar from "./Sidebar";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { 
  Home, 
  Briefcase, 
  User, 
  FileText, 
  KanbanSquare, 
  Compass, 
  MessageSquareCode,
  Menu,
  X
} from "lucide-react";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [isClient, setIsClient] = useState(false);
  
  const pathname = usePathname();
  const router = useRouter();

  // Route flags
  const isAuthPage = pathname === "/welcome" || pathname === "/onboarding";

  useEffect(() => {
    setIsClient(true);

    const checkAuth = () => {
      const logged = localStorage.getItem("isLoggedIn") === "true";
      setIsLoggedIn(logged);

      // Redirect if not logged in and not on the welcome page
      if (!logged && pathname !== "/welcome") {
        router.push("/welcome");
      }
    };

    checkAuth();

    // Listen to storage mutations (login / logout)
    window.addEventListener("storage", checkAuth);
    return () => window.removeEventListener("storage", checkAuth);
  }, [pathname, router]);

  // Close mobile menu when routing changes
  useEffect(() => {
    setIsMobileMenuOpen(false);
  }, [pathname]);

  const navItems = [
    { label: "Dashboard", href: "/", icon: Home },
    { label: "Job Discovery", href: "/jobs", icon: Briefcase },
    { label: "CV & Profile", href: "/profile", icon: User },
    { label: "Document Hub", href: "/documents", icon: FileText },
    { label: "Application Tracker", href: "/tracker", icon: KanbanSquare },
    { label: "Career Roadmap", href: "/roadmap", icon: Compass },
    { label: "Interview Prep", href: "/interview", icon: MessageSquareCode },
  ];

  // Prevent flash before hydration
  if (!isClient) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh", background: "var(--bg-dark)" }}>
        <div className="status-dot active" style={{ width: 12, height: 12 }}></div>
      </div>
    );
  }

  // Render without sidebar for login & onboarding
  if (isAuthPage) {
    return (
      <div className="app-container" style={{ width: "100vw" }}>
        <main 
          className="main-content animate-fade-in" 
          style={{ marginLeft: 0, padding: 0, width: "100vw", maxWidth: "100%" }}
        >
          {children}
        </main>
      </div>
    );
  }

  return (
    <div className="app-container">
      {/* Sidebar for Desktop */}
      <Sidebar onCollapseToggle={setIsCollapsed} />

      {/* Mobile Menu Overlay Toggle Button */}
      <div 
        style={{
          position: "fixed",
          top: 16,
          right: 20,
          zIndex: 101,
          display: "none"
        }}
        className="mobile-toggle-btn"
      >
        <button
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          style={{
            background: "rgba(10, 13, 28, 0.85)",
            backdropFilter: "blur(12px)",
            border: "1px solid var(--border-color)",
            padding: 8,
            borderRadius: 8,
            color: "var(--text-primary)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center"
          }}
        >
          {isMobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>

      {/* Mobile Drawer Menu */}
      {isMobileMenuOpen && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            width: "100vw",
            height: "100vh",
            background: "rgba(7, 9, 19, 0.95)",
            backdropFilter: "blur(20px)",
            zIndex: 98,
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            alignItems: "center",
            gap: 24,
            animation: "fadeIn 0.2s ease"
          }}
        >
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 16,
                  fontSize: 20,
                  fontWeight: 600,
                  color: isActive ? "var(--primary)" : "var(--text-secondary)",
                  padding: "10px 20px",
                  borderRadius: 8,
                  background: isActive ? "rgba(99, 102, 241, 0.1)" : "transparent",
                  transition: "all 0.2s"
                }}
              >
                <Icon size={24} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </div>
      )}

      {/* Main Content Area */}
      <main 
        className="main-content animate-fade-in" 
        style={{
          marginLeft: isCollapsed ? "var(--sidebar-collapsed-width)" : "var(--sidebar-width)"
        }}
      >
        {children}
      </main>
    </div>
  );
}
