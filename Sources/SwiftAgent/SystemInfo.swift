//
//  SystemInfo.swift
//  SwiftAgent
//
//  Created by Norikazu Muramoto on 2025/01/11.
//

import Foundation

/// Represents detailed system information needed for the agent
public struct SystemInfo: CustomStringConvertible {
    /// Operating system name and version
    public let platform: String
    
    /// Operating system version
    public let version: String
    
    /// Application directory path
    public let applicationDirectory: String
    
    /// Documents directory path
    public let documentsDirectory: String
    
    /// Current working directory
    public let currentWorkingDirectory: String
    
    /// Current date in yyyy-MM-dd format
    public let currentDate: String
    
    /// Current time in HH:mm:ss format
    public let currentTime: String
    
    /// Creates system information
    public init() {
        let processInfo = ProcessInfo.processInfo
        
        // Platform info
#if os(iOS)
        self.platform = "iOS"
#elseif os(macOS)
        self.platform = "macOS"
#elseif os(tvOS)
        self.platform = "tvOS"
#elseif os(watchOS)
        self.platform = "watchOS"
#else
        self.platform = "Unknown"
#endif
        
        // Version info
        self.version = processInfo.operatingSystemVersionString
        
        // Directory paths
        let fileManager = FileManager.default
        
        // Get application directory
        if let appSupportURL = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask).first {
            self.applicationDirectory = appSupportURL.path
        } else {
            self.applicationDirectory = NSTemporaryDirectory()
        }
        
        // Get documents directory
        if let documentsURL = fileManager.urls(for: .documentDirectory, in: .userDomainMask).first {
            self.documentsDirectory = documentsURL.path
        } else {
            self.documentsDirectory = NSTemporaryDirectory()
        }
        
        // Current working directory (with fallback)
        if let cwd = fileManager.currentDirectoryPath as String? {
            self.currentWorkingDirectory = cwd
        } else {
            self.currentWorkingDirectory = NSTemporaryDirectory()
        }
        
        // Date and time formatting
        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd"
        let timeFormatter = DateFormatter()
        timeFormatter.dateFormat = "HH:mm:ss"
        let now = Date()
        
        self.currentDate = dateFormatter.string(from: now)
        self.currentTime = timeFormatter.string(from: now)
    }
    
    /// Creates system information with custom values (primarily for testing)
    public init(
        platform: String,
        version: String,
        applicationDirectory: String,
        documentsDirectory: String,
        currentWorkingDirectory: String,
        currentDate: String,
        currentTime: String
    ) {
        self.platform = platform
        self.version = version
        self.applicationDirectory = applicationDirectory
        self.documentsDirectory = documentsDirectory
        self.currentWorkingDirectory = currentWorkingDirectory
        self.currentDate = currentDate
        self.currentTime = currentTime
    }
    
    /// Provides a human-readable description of the system information
    public var description: String {
        """
        [SYSTEM INFORMATION]:
        Platform: \(platform)
        Version: \(version)
        Application Directory: \(applicationDirectory)
        Documents Directory: \(documentsDirectory)
        Current Working Directory: \(currentWorkingDirectory)
        Current Date: \(currentDate)
        Current Time: \(currentTime)
        """
    }
}

// Extension to provide non-main actor interface
extension SystemInfo {
    /// Non-isolated description that can be accessed from any context
    public func descriptionFromAnyContext() -> String {
        // Since description only accesses immutable properties, it's safe to call from any context
        description
    }
}
