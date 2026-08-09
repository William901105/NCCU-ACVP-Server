using System.Threading.Tasks;
using Moq;
using NIST.CVP.ACVTS.Libraries.Crypto.Common.Asymmetric.LMS.Native.Enums;
using NIST.CVP.ACVTS.Libraries.Crypto.Common.Asymmetric.LMS.Native.Keys;
using NUnit.Framework;
using NIST.CVP.ACVTS.Libraries.Generation.LMS.SP800_208.SigGen;
using NIST.CVP.ACVTS.Libraries.Oracle.Abstractions;
using NIST.CVP.ACVTS.Libraries.Oracle.Abstractions.ParameterTypes.Lms;
using NIST.CVP.ACVTS.Libraries.Oracle.Abstractions.ResultTypes;
using NIST.CVP.ACVTS.Libraries.Math;
using NIST.CVP.ACVTS.Libraries.Math.Domain;

namespace NIST.CVP.ACVTS.Libraries.Generation.Tests.LMS.SP800_208.SigGen;

[TestFixture]
public class TestCaseGeneratorAftTests
{
    private Mock<IOracle> _mockOracle;
    private TestCaseGeneratorAft _generator;

    [SetUp]
    public void Setup()
    {
        _mockOracle = new Mock<IOracle>();
        _generator = new TestCaseGeneratorAft(_mockOracle.Object);
    }

    [Test]
    public void PrepareGenerator_SetsUpMessageLengthsForH5()
    {
        // Arrange
        var group = new TestGroup
        {
            MessageLength = new MathDomain().AddSegment(new RangeDomainSegment(new Mock<IRandom800_90>().Object, 10, 101)),
            LmsMode = LmsMode.LMS_SHA256_M24_H5
        };

        // Act
        var response = _generator.PrepareGenerator(group, false);

        // Assert
        Assert.That(response, Is.Not.Null);
        Assert.That(_generator.NumberOfTestCasesToGenerate, Is.EqualTo(32));
    }
    
    [Test]
    public void PrepareGenerator_SetsUpMessageLengthsForNonH5()
    {
        // Arrange
        var group = new TestGroup
        {
            MessageLength = new MathDomain().AddSegment(new RangeDomainSegment(new Mock<IRandom800_90>().Object, 10, 101)),
            LmsMode = LmsMode.LMS_SHA256_M24_H10
        };

        // This value should not be modified by PrepareGenerator
        var casesToGenerate = _generator.NumberOfTestCasesToGenerate;
        
        // Act
        var response = _generator.PrepareGenerator(group, false);

        // Assert
        Assert.That(response, Is.Not.Null);
        Assert.That(_generator.NumberOfTestCasesToGenerate, Is.EqualTo(casesToGenerate));
    }

    [Test]
    public async Task GenerateAsync_IsSample_CallsOracleWithKeyPair()
    {
        // Arrange
        var group = new TestGroup
        {
            MessageLength = new MathDomain().AddSegment(new RangeDomainSegment(new Mock<IRandom800_90>().Object, 32, 33)),
            KeyPair = new Mock<ILmsKeyPair>().Object,
            LmsMode = LmsMode.LMS_SHA256_M24_H5
        };
        _generator.PrepareGenerator(group, true);

        var result = new LmsSignatureResult
        {
            Message = new BitString("AABBCCDD"),
            Signature = new BitString("FFEEDDCC")
        };
        _mockOracle.Setup(o => o.GetLmsSignatureCaseAsync(It.IsAny<LmsSignatureParameters>())).ReturnsAsync(result);

        // Act
        var response = await _generator.GenerateAsync(group, true);

        // Assert
        Assert.That(response.TestCase, Is.Not.Null);
        Assert.That(response.TestCase.Message, Is.EqualTo(result.Message));
        Assert.That(response.TestCase.Signature, Is.EqualTo(result.Signature));
        _mockOracle.Verify(o => o.GetLmsSignatureCaseAsync(It.IsAny<LmsSignatureParameters>()), Times.Once);
    }

    [Test]
    public async Task GenerateAsync_IsNotSample_CallsDeferredOracle()
    {
        // Arrange
        var group = new TestGroup
        {
            MessageLength = new MathDomain().AddSegment(new RangeDomainSegment(new Mock<IRandom800_90>().Object, 32, 33)),
            LmsMode = LmsMode.LMS_SHA256_M24_H5
        };
        _generator.PrepareGenerator(group, false);

        var result = new LmsSignatureResult
        {
            Message = new BitString("AABBCCDD"),
            Signature = new BitString("FFEEDDCC")
        };
        _mockOracle.Setup(o => o.GetDeferredLmsSignatureCaseAsync(It.IsAny<LmsSignatureParameters>())).ReturnsAsync(result);

        // Act
        var response = await _generator.GenerateAsync(group, false);

        // Assert
        Assert.That(response.TestCase, Is.Not.Null);
        Assert.That(response.TestCase.Message, Is.EqualTo(result.Message));
        _mockOracle.Verify(o => o.GetDeferredLmsSignatureCaseAsync(It.IsAny<LmsSignatureParameters>()), Times.Once);
    }
}
