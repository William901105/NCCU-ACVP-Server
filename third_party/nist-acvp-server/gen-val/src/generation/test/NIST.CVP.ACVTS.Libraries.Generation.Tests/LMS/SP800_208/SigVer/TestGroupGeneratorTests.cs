using System.Threading.Tasks;
using Moq;
using NUnit.Framework;
using NIST.CVP.ACVTS.Libraries.Crypto.Common.Asymmetric.LMS.Native.Enums;
using NIST.CVP.ACVTS.Libraries.Generation.LMS.SP800_208.SigVer;
using NIST.CVP.ACVTS.Libraries.Oracle.Abstractions;
using NIST.CVP.ACVTS.Libraries.Oracle.Abstractions.ParameterTypes.Lms;
using NIST.CVP.ACVTS.Libraries.Oracle.Abstractions.ResultTypes;
using NIST.CVP.ACVTS.Libraries.Crypto.Common.Asymmetric.LMS.Native.Keys;
using NIST.CVP.ACVTS.Libraries.Generation.LMS.SP800_208.Shared;
using NIST.CVP.ACVTS.Libraries.Math.Domain;

namespace NIST.CVP.ACVTS.Libraries.Generation.Tests.LMS.SP800_208.SigVer;

[TestFixture]
public class TestGroupGeneratorTests
{
    private Mock<IOracle> _mockOracle;
    private TestGroupGenerator _generator;

    [SetUp]
    public void Setup()
    {
        _mockOracle = new Mock<IOracle>();
        _generator = new TestGroupGenerator(_mockOracle.Object);
    }

    [Test]
    public async Task BuildTestGroupsAsync_WithSpecificCapabilities_ReturnsCorrectGroups()
    {
        // Arrange
        var parameters = new Parameters
        {
            SpecificCapabilities =
            [
                new SpecificCapability
                {
                    LmsMode = LmsMode.LMS_SHA256_M24_H5,
                    LmOtsMode =  LmOtsMode.LMOTS_SHA256_N24_W1
                }
            ],
            MessageLength = new MathDomain().AddSegment(new ValueDomainSegment(1024)),
            IsSample = false
        };

        var mockKeyPair = new Mock<ILmsKeyPair>();
        mockKeyPair.Setup(k => k.PublicKey.Key).Returns([0x01, 0x02]);
        
        _mockOracle.Setup(o => o.GetLmsKeyCaseAsync(It.IsAny<LmsKeyPairParameters>())).ReturnsAsync(new LmsKeyPairResult { KeyPair = mockKeyPair.Object });
        
        // Act
        var result = await _generator.BuildTestGroupsAsync(parameters);

        // Assert
        Assert.That(result, Has.Count.EqualTo(1));
        Assert.That(result[0].LmsMode, Is.EqualTo(LmsMode.LMS_SHA256_M24_H5));
        Assert.That(result[0].LmOtsMode, Is.EqualTo(LmOtsMode.LMOTS_SHA256_N24_W1));
        Assert.That(result[0].TestType, Is.EqualTo("AFT"));
    }

    [Test]
    public async Task BuildTestGroupsAsync_CallsOracleAndSetsKeyPair()
    {
        // Arrange
        var parameters = new Parameters
        {
            SpecificCapabilities =
            [
                new SpecificCapability
                {
                    LmsMode = LmsMode.LMS_SHA256_M24_H5,
                    LmOtsMode =  LmOtsMode.LMOTS_SHA256_N24_W1
                }
            ],
            MessageLength = new MathDomain().AddSegment(new ValueDomainSegment(1024)),
            IsSample = true
        };

        var mockKeyPair = new Mock<ILmsKeyPair>();
        mockKeyPair.Setup(k => k.PublicKey.Key).Returns([0x01, 0x02]);
        
        _mockOracle.Setup(o => o.GetLmsKeyCaseAsync(It.IsAny<LmsKeyPairParameters>())).ReturnsAsync(new LmsKeyPairResult { KeyPair = mockKeyPair.Object });

        // Act
        var result = await _generator.BuildTestGroupsAsync(parameters);

        // Assert
        Assert.That(result, Has.Count.EqualTo(1));
        Assert.That(result[0].KeyPair, Is.Not.Null);
        _mockOracle.Verify(o => o.GetLmsKeyCaseAsync(It.IsAny<LmsKeyPairParameters>()), Times.Once);
    }
}
