name := "hoge-ntt-merged"

scalaVersion := "2.13.12"

addCompilerPlugin("edu.berkeley.cs" % "chisel3-plugin" % "3.6.1" cross CrossVersion.full)

resolvers ++= Resolver.sonatypeOssRepos("releases")

libraryDependencies ++= Seq(
    "edu.berkeley.cs" %% "chisel3" % "3.6.1"
)

scalacOptions ++= Seq(
      "-Xsource:2.13",
      "-language:reflectiveCalls",
      "-deprecation",
      "-feature",
      "-Xcheckinit"
      // Enables autoclonetype2 in 3.4.x (on by default in 3.5)
    //   "-P:chiselplugin:useBundlePlugin"
    )

Compile / run / mainClass := Some("hoge.HogeTops")
