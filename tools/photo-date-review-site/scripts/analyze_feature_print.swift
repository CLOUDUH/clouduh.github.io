#!/usr/bin/env swift

import Foundation
import ImageIO
import Vision

let root = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
let manifestURL = root.appendingPathComponent("public/calibration/calibration-items.json")
let raw = try Data(contentsOf: manifestURL)
let doc = try JSONSerialization.jsonObject(with: raw) as! [String: Any]
let items = doc["items"] as! [[String: Any]]

func feature(_ item: [String: Any]) throws -> VNFeaturePrintObservation {
    let id = item["id"] as! String
    let url = root.appendingPathComponent("public/calibration/thumbs/\(id).jpg")
    guard let src = CGImageSourceCreateWithURL(url as CFURL, nil),
          let cg = CGImageSourceCreateImageAtIndex(src, 0, nil) else {
        throw NSError(domain: "feature", code: 1)
    }
    let req = VNGenerateImageFeaturePrintRequest()
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    try handler.perform([req])
    return req.results!.first as! VNFeaturePrintObservation
}

let requested = Set(CommandLine.arguments.dropFirst())
let targets = items.filter {
    let rel = $0["relativePath"] as! String
    let name = $0["filename"] as! String
    return requested.contains(rel) || requested.contains(name)
}

var cache: [String: VNFeaturePrintObservation] = [:]
for item in items {
    let rel = item["relativePath"] as! String
    cache[rel] = try feature(item)
}

for target in targets {
    let rel = target["relativePath"] as! String
    let base = cache[rel]!
    var ranked: [(Float, [String: Any])] = []
    for item in items {
        let other = item["relativePath"] as! String
        if other == rel { continue }
        var distance: Float = 0
        try base.computeDistance(&distance, to: cache[other]!)
        ranked.append((distance, item))
    }
    ranked.sort { $0.0 < $1.0 }
    print("TARGET\t\(rel)")
    for (distance, item) in ranked.prefix(20) {
        print(String(format: "%.6f\t%@\t%@", distance,
                     item["captureDate"] as! String,
                     item["relativePath"] as! String))
    }
}
