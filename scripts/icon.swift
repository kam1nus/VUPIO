import AppKit

let input = URL(fileURLWithPath: CommandLine.arguments[1])
let dest = URL(fileURLWithPath: CommandLine.arguments[2], isDirectory: true)
guard let vector = NSImage(contentsOf: input) else {
    fatalError("Could not read the VUPIO SVG icon")
}

func render(_ size: Int, opaque: Bool = false) -> Data {
    guard let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size,
                                        bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                                        colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0),
          let context = NSGraphicsContext(bitmapImageRep: bitmap) else {
        fatalError("Icon buffer unavailable")
    }
    let rect = NSRect(x: 0, y: 0, width: size, height: size)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = context
    context.imageInterpolation = .high
    if opaque {
        NSColor(srgbRed: 17.0 / 255, green: 24.0 / 255, blue: 39.0 / 255, alpha: 1).setFill()
        rect.fill()
    }
    vector.draw(in: rect, from: .zero, operation: .sourceOver, fraction: 1)
    context.flushGraphics()
    NSGraphicsContext.restoreGraphicsState()
    return bitmap.representation(using: .png, properties: [:])!
}

try FileManager.default.createDirectory(at: dest, withIntermediateDirectories: true)
for edge in [16, 32, 128, 256, 512] {
    for scale in [1, 2] {
        let suffix = scale == 2 ? "@2x" : ""
        try render(edge * scale).write(to: dest.appendingPathComponent("icon_\(edge)x\(edge)\(suffix).png"))
    }
}
if CommandLine.arguments.count > 3 {
    let web = URL(fileURLWithPath: CommandLine.arguments[3], isDirectory: true)
    for size in [24, 48, 64] {
        try render(size).write(to: dest.appendingPathComponent("icon_\(size)x\(size).png"))
    }
    for (name, size) in [("apple-touch-icon", 180), ("vupio-icon-192", 192), ("vupio-icon-512", 512)] {
        try render(size, opaque: true).write(to: web.appendingPathComponent(name + ".png"))
    }
}
