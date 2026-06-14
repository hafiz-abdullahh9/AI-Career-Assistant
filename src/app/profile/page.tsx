"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  UploadCloud,
  User,
  Mail,
  Phone,
  Briefcase,
  MapPin,
  Sparkles,
  BookOpen,
  Plus,
  Trash2,
  CheckCircle,
  FileText,
  Clock,
  Save,
  Check,
} from "lucide-react";
import styles from "./Profile.module.css";

interface Experience {
  id: string;
  role: string;
  company: string;
  duration: string;
  desc: string;
}

export default function ProfilePage() {
  const fileInputRef = useRef<HTMLInputElement>(null);

  // States
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadLogs, setUploadLogs] = useState<string[]>([]);
  const [fileName, setFileName] = useState("");

  const [hasProfile, setHasProfile] = useState(true); // Default profile loaded

  // Form Fields
  const [name, setName] = useState("John Doe");
  const [email, setEmail] = useState("john.doe@example.com");
  const [phone, setPhone] = useState("+92 300 1234567");
  const [location, setLocation] = useState("Karachi, Pakistan (Open to Remote)");
  const [bio, setBio] = useState(
    "Passionate Frontend Engineer with 2+ years of experience crafting modern, accessible web interfaces. Specializing in React, TypeScript, and Next.js, with a focus on writing clean, semantic HTML and structural CSS."
  );

  const [skills, setSkills] = useState([
    "React",
    "Next.js",
    "TypeScript",
    "CSS Modules",
    "Git",
    "REST APIs",
    "JavaScript",
    "HTML5",
    "Node.js",
  ]);
  const [newSkill, setNewSkill] = useState("");

  const [experiences, setExperiences] = useState<Experience[]>([
    {
      id: "exp-1",
      role: "Frontend Developer",
      company: "TechCorp Solutions",
      duration: "June 2024 - Present",
      desc: "Developed and optimized modular SaaS dashboards using Next.js. Reduced bundle sizes by 32% using dynamic imports and refactored global states. Collaborated on accessibility audit campaigns complying with WCAG 2.1 standards.",
    },
    {
      id: "exp-2",
      role: "Frontend Engineer Intern",
      company: "DevSoft Hub",
      duration: "November 2023 - May 2024",
      desc: "Built responsive landing pages and integrated RESTful endpoints with React hooks. Maintained code quality through automated Jest test suites and participated in daily scrum updates.",
    },
  ]);

  const [education, setEducation] = useState("Bachelor of Computer Science");
  const [institution, setInstitution] = useState("DHA Suffa University");
  const [gradYear, setGradYear] = useState("2025");

  const [showSavedToast, setShowSavedToast] = useState(false);

  useEffect(() => {
    // Dynamic retrieval from onboarding fields in local storage
    const storedName = localStorage.getItem("userName");
    if (storedName) setName(storedName);

    const storedCountry = localStorage.getItem("userCountry");
    const storedJobTitle = localStorage.getItem("userJobTitle");
    if (storedCountry) {
      if (storedJobTitle) {
        setLocation(`${storedCountry} (Open to remote ${storedJobTitle} roles)`);
      } else {
        setLocation(`${storedCountry} (Open to Remote)`);
      }
    }

    const storedGoals = localStorage.getItem("userGoals");
    if (storedGoals) setBio(storedGoals);

    const storedDegree = localStorage.getItem("userDegree");
    if (storedDegree) setEducation(storedDegree);

    const storedInstitution = localStorage.getItem("userInstitution");
    if (storedInstitution) setInstitution(storedInstitution);

    const storedCvName = localStorage.getItem("userCvName");
    if (storedCvName) setFileName(storedCvName);
  }, []);

  // Handlers
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      processFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      processFile(e.target.files[0]);
    }
  };

  const triggerFileSelect = () => {
    fileInputRef.current?.click();
  };

  const processFile = (file: File) => {
    setFileName(file.name);
    setIsUploading(true);
    setUploadProgress(0);
    setUploadLogs([]);

    const steps = [
      { progress: 15, log: "Initializing document analyzer..." },
      { progress: 35, log: "Parsing PDF binary layout and structural mapping..." },
      { progress: 55, log: "AI Model detecting sections (Experience, Skills, Education)..." },
      { progress: 75, log: "Extracting work histories and company names..." },
      { progress: 90, log: "Normalizing skills tags and matching with database standard..." },
      { progress: 100, log: "Profile extraction completed successfully!" },
    ];

    steps.forEach((step, idx) => {
      setTimeout(() => {
        setUploadProgress(step.progress);
        setUploadLogs((prev) => [...prev, `[system] ${step.log}`]);

        if (step.progress === 100) {
          setTimeout(() => {
            setIsUploading(false);
            // Simulate filling extracted values (e.g. updating profile details slightly)
            setName("John Doe (CV Analyzed)");
            setSkills((prev) => Array.from(new Set([...prev, "Redux", "GraphQL"])));
            setUploadLogs([]);
          }, 1000);
        }
      }, (idx + 1) * 800);
    });
  };

  const addSkill = (e: React.FormEvent) => {
    e.preventDefault();
    if (newSkill.trim() && !skills.includes(newSkill.trim())) {
      setSkills([...skills, newSkill.trim()]);
      setNewSkill("");
    }
  };

  const deleteSkill = (skillToDelete: string) => {
    setSkills(skills.filter((s) => s !== skillToDelete));
  };

  const deleteExperience = (id: string) => {
    setExperiences(experiences.filter((exp) => exp.id !== id));
  };

  const saveProfile = () => {
    // Save to local storage
    localStorage.setItem("userName", name);
    localStorage.setItem("userGoals", bio);
    localStorage.setItem("userDegree", education);
    localStorage.setItem("userInstitution", institution);
    localStorage.setItem("userCvName", fileName);

    setShowSavedToast(true);
    setTimeout(() => setShowSavedToast(false), 3000);
  };

  return (
    <div className={styles.container}>
      {/* Header */}
      <header className={styles.sectionHeader}>
        <h1>CV Upload & Professional Profile</h1>
        <p>
          Upload your CV to let the AI analysis agent extract your profile details, or manage your structured profile directly below.
        </p>
      </header>

      {/* CV Uploader Zone */}
      {!isUploading ? (
        <div
          className={`${styles.uploadZone} glass`}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
          onClick={triggerFileSelect}
        >
          <input
            type="file"
            ref={fileInputRef}
            className="hidden"
            style={{ display: "none" }}
            accept=".pdf,.docx,.txt"
            onChange={handleFileSelect}
          />
          <div className={styles.uploadIcon}>
            <UploadCloud size={28} />
          </div>
          <div>
            <span className={styles.uploadTitle}>Drag & Drop your CV here</span>
            <p className={styles.uploadDesc}>Supports PDF, DOCX, and TXT formats (Max 5MB)</p>
          </div>
          {fileName && (
            <div style={{ fontSize: 13, color: "var(--secondary)", fontWeight: 600 }}>
              Last Uploaded: {fileName}
            </div>
          )}
        </div>
      ) : (
        <div className={`${styles.progressCard} glass`}>
          <div className={styles.progressHeader}>
            <span className={styles.progressTitle}>
              <Clock size={16} className="animate-float" style={{ color: "var(--primary)" }} />
              <span>AI Agent Parsing CV: {fileName}</span>
            </span>
            <span className={styles.progressPercent}>{uploadProgress}%</span>
          </div>
          <div className={styles.barBack}>
            <div className={styles.barFill} style={{ width: `${uploadProgress}%` }}></div>
          </div>
          <div className={styles.stepLog}>
            {uploadLogs.map((log, i) => (
              <div key={i} style={{ marginBottom: 4 }}>
                {log}
              </div>
            ))}
            <div className="status-dot active" style={{ width: 6, height: 6, marginRight: 6 }}></div>
            <span style={{ color: "var(--text-muted)", fontSize: 11 }}>Waiting for next process token...</span>
          </div>
        </div>
      )}

      {/* Interactive Form */}
      {hasProfile && (
        <div className={styles.profileLayout}>
          {/* Main profile section */}
          <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
            {/* Bio info */}
            <div className={`${styles.formCard} glass`}>
              <h3 className={styles.cardTitle}>
                <User size={18} style={{ color: "var(--primary)" }} />
                <span>Basic Profile Information</span>
              </h3>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                <div className={styles.fieldGroup}>
                  <label className={styles.fieldLabel}>Full Name</label>
                  <input
                    type="text"
                    className={styles.inputControl}
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                </div>
                <div className={styles.fieldGroup}>
                  <label className={styles.fieldLabel}>Email Address</label>
                  <input
                    type="email"
                    className={styles.inputControl}
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                <div className={styles.fieldGroup}>
                  <label className={styles.fieldLabel}>Phone Number</label>
                  <input
                    type="text"
                    className={styles.inputControl}
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                  />
                </div>
                <div className={styles.fieldGroup}>
                  <label className={styles.fieldLabel}>Location Preference</label>
                  <input
                    type="text"
                    className={styles.inputControl}
                    value={location}
                    onChange={(e) => setLocation(e.target.value)}
                  />
                </div>
              </div>

              <div className={styles.fieldGroup}>
                <label className={styles.fieldLabel}>Professional Bio</label>
                <textarea
                  className={styles.textareaControl}
                  value={bio}
                  onChange={(e) => setBio(e.target.value)}
                />
              </div>
            </div>

            {/* Experience Block */}
            <div className={`${styles.formCard} glass`}>
              <h3 className={styles.cardTitle}>
                <Briefcase size={18} style={{ color: "var(--secondary)" }} />
                <span>Work Experience Timeline</span>
              </h3>

              <div className={styles.experienceBlock}>
                {experiences.map((exp) => (
                  <div key={exp.id} className={styles.experienceItem}>
                    <div className={styles.experienceItemHeader}>
                      <div>
                        <h4 className={styles.experienceRole}>{exp.role}</h4>
                        <span className={styles.experienceCompDate}>
                          {exp.company} • {exp.duration}
                        </span>
                      </div>
                    </div>
                    <p className={styles.experienceDesc}>{exp.desc}</p>
                    <button
                      className={styles.deleteItemBtn}
                      onClick={() => deleteExperience(exp.id)}
                      title="Delete experience"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
              </div>
              <button
                className={styles.secondaryBtn}
                style={{ alignSelf: "flex-start", padding: "8px 16px" }}
                onClick={() =>
                  setExperiences([
                    ...experiences,
                    {
                      id: `exp-${Date.now()}`,
                      role: "Software Engineer",
                      company: "New Company",
                      duration: "2024 - Present",
                      desc: "Click to edit and add your achievements and core responsibilities.",
                    },
                  ])
                }
              >
                <Plus size={16} />
                <span>Add Work Experience</span>
              </button>
            </div>
          </div>

          {/* Sidebar profile widgets */}
          <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
            {/* Skills tag editor */}
            <div className={`${styles.formCard} glass`}>
              <h3 className={styles.cardTitle}>
                <Sparkles size={18} style={{ color: "var(--accent)" }} />
                <span>Skills Inventory</span>
              </h3>

              <div className={styles.tagsList}>
                {skills.map((skill, idx) => (
                  <span key={idx} className={styles.tagPill}>
                    <span>{skill}</span>
                    <span className={styles.tagDeleteBtn} onClick={() => deleteSkill(skill)}>
                      <Trash2 size={11} style={{ strokeWidth: 3 }} />
                    </span>
                  </span>
                ))}
              </div>

              <form onSubmit={addSkill} className={styles.skillsAddRow}>
                <input
                  type="text"
                  placeholder="Add custom skill..."
                  className={styles.inputControl}
                  style={{ padding: "8px 12px", fontSize: 13 }}
                  value={newSkill}
                  onChange={(e) => setNewSkill(e.target.value)}
                />
                <button type="submit" className={styles.addBtn}>
                  <Plus size={14} />
                </button>
              </form>
            </div>

            {/* Education Info */}
            <div className={`${styles.formCard} glass`}>
              <h3 className={styles.cardTitle}>
                <BookOpen size={18} style={{ color: "var(--warning)" }} />
                <span>Education</span>
              </h3>

              <div className={styles.fieldGroup} style={{ gap: 12 }}>
                <div className={styles.fieldGroup}>
                  <label className={styles.fieldLabel}>Degree</label>
                  <input
                    type="text"
                    className={styles.inputControl}
                    value={education}
                    onChange={(e) => setEducation(e.target.value)}
                  />
                </div>
                <div className={styles.fieldGroup}>
                  <label className={styles.fieldLabel}>Institution</label>
                  <input
                    type="text"
                    className={styles.inputControl}
                    value={institution}
                    onChange={(e) => setInstitution(e.target.value)}
                  />
                </div>
                <div className={styles.fieldGroup}>
                  <label className={styles.fieldLabel}>Graduation Year</label>
                  <input
                    type="text"
                    className={styles.inputControl}
                    value={gradYear}
                    onChange={(e) => setGradYear(e.target.value)}
                  />
                </div>
              </div>
            </div>

            {/* Save Profile Button */}
            <button className={styles.saveBtn} onClick={saveProfile}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Save size={16} />
                <span>Save Profile Changes</span>
              </div>
            </button>

            {/* Saved indicator toast */}
            {showSavedToast && (
              <div
                style={{
                  background: "var(--success)",
                  color: "var(--bg-dark)",
                  padding: "12px 16px",
                  borderRadius: 8,
                  fontWeight: 700,
                  fontSize: 13,
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  boxShadow: "0 4px 15px var(--success-glow)",
                  animation: "slideUp 0.3s ease",
                }}
              >
                <Check size={16} style={{ strokeWidth: 3 }} />
                <span>Profile Changes Saved Securely</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
