// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "CrewBusKit",
    platforms: [.macOS(.v14), .iOS(.v17)],
    products: [
        .library(name: "CrewBusKit", targets: ["CrewBusKit"]),
    ],
    targets: [
        .target(name: "CrewBusKit"),
    ]
)
