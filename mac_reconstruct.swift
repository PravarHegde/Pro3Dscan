import Foundation
import RealityKit
import Metal

// Ensure we are on macOS 12.0 or newer
guard #available(macOS 12.0, *) else {
    print("Error: Object Capture requires macOS 12.0 or newer.")
    exit(1)
}

// Check for arguments
guard CommandLine.arguments.count >= 3 else {
    print("Usage: mac_reconstruct <input_folder> <output_file>")
    exit(1)
}

let inputFolder = URL(fileURLWithPath: CommandLine.arguments[1])
let outputFile = URL(fileURLWithPath: CommandLine.arguments[2])

// Make sure Metal is available
guard MTLCreateSystemDefaultDevice() != nil else {
    print("Error: Metal is not supported on this Mac. Object Capture requires Metal.")
    exit(1)
}

// Check PhotogrammetrySession support
guard PhotogrammetrySession.isSupported else {
    print("Error: PhotogrammetrySession is not supported on this Mac hardware.")
    exit(1)
}

var configuration = PhotogrammetrySession.Configuration()
configuration.sampleOrdering = .unordered

do {
    let session = try PhotogrammetrySession(input: inputFolder, configuration: configuration)
    
    let waiter = DispatchGroup()
    waiter.enter()
    
    Task {
        for try await output in session.outputs {
            switch output {
            case .requestProgress(_, let fractionComplete):
                let percentage = String(format: "%.2f", fractionComplete * 100)
                print("Progress: \(percentage)%")
            case .requestComplete(_, _):
                print("Model Generated Successfully!")
            case .requestError(_, let error):
                print("Reconstruction Error: \(error)")
                exit(1)
            case .processingComplete:
                print("Processing Complete!")
                waiter.leave()
            @unknown default:
                break
            }
        }
    }
    
    // Add the request
    try session.process(requests: [
        .modelFile(url: outputFile, detail: .full)
    ])
    
    waiter.wait()
    print("Saved 3D mesh to: \(outputFile.path)")
    
} catch {
    print("Failed to start session: \(error)")
    exit(1)
}
