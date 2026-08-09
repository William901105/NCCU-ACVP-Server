using NIST.CVP.ACVTS.Libraries.Crypto.Common.Asymmetric.LMS.Native.Enums;
using NIST.CVP.ACVTS.Libraries.Generation.LMS.SP800_208.Shared;
using NIST.CVP.ACVTS.Libraries.Math.Domain;
using NIST.CVP.ACVTS.Tests.Core.TestCategoryAttributes;
using NUnit.Framework;

namespace NIST.CVP.ACVTS.Libraries.Generation.Tests.LMS.SP800_208.Shared
{
    [TestFixture, UnitTest]
    public class ParameterValidatorTests
    {
        private readonly ParameterValidator _subject = new();

        [Test]
        public void WhenGivenDefaultParameterBuilder_ShouldPass()
        {
            var pb = new ParameterBuilder();
            var p = pb.Build();
            var result = _subject.Validate(p);
            Assert.That(result.Success, Is.True, result.ErrorMessage);
        }

        [Test]
        [TestCase("LMS", "sigGen", "SP800-208", true)]
        [TestCase("LMS", "sigVer", "SP800-208", true)]
        [TestCase("LMS", "KeyGen", "SP800-208", false)]
        [TestCase(null, null, null, false)]
        public void WhenGivenAlgoModeRevision_ShouldVerifyOnlyValidCombinations(string algo, string mode, string revision, bool expectedSuccess)
        {
            var pb = new ParameterBuilder().WithAlgoModeRevision(algo, mode, revision);
            var p = pb.Build();
            var result = _subject.Validate(p);
            Assert.That(result.Success, Is.EqualTo(expectedSuccess), result.ErrorMessage);
        }

        [Test]
        public void WhenGivenValidGeneralAndSpecificCapabilities_ShouldFail()
        {
            var pb = new ParameterBuilder()
                .WithGeneralCapabilities(new GeneralCapabilities
                {
                    LmsModes = [LmsMode.LMS_SHA256_M24_H5],
                    LmOtsModes = [LmOtsMode.LMOTS_SHA256_N24_W1]
                })
                .WithSpecificCapabilities([new SpecificCapability { LmsMode = LmsMode.LMS_SHA256_M24_H5, LmOtsMode = LmOtsMode.LMOTS_SHA256_N24_W1 }]);

            var p = pb.Build();
            var result = _subject.Validate(p);
            Assert.That(result.Success, Is.False,  result.ErrorMessage);
        }
        
        [Test]
        public void WhenGivenSpecificCapabilities_AllValid_ShouldPass()
        {
            var capabilities = new SpecificCapability[]
            {
                new() { LmsMode = LmsMode.LMS_SHA256_M24_H5, LmOtsMode = LmOtsMode.LMOTS_SHA256_N24_W1 },
                new() { LmsMode = LmsMode.LMS_SHA256_M24_H5, LmOtsMode = LmOtsMode.LMOTS_SHA256_N24_W2 }
            };
            
            var pb = new ParameterBuilder()
                .WithSpecificCapabilities(capabilities)
                .WithGeneralCapabilities(null);
            
            var p = pb.Build();
            var result = _subject.Validate(p);
            Assert.That(result.Success, Is.True, result.ErrorMessage);
        }
        
        [Test]
        public void WhenGivenGeneralCapabilities_AllValid_ShouldPass()
        {
            var capabilities = new GeneralCapabilities
            {
                LmsModes = [LmsMode.LMS_SHA256_M24_H5], 
                LmOtsModes = [LmOtsMode.LMOTS_SHA256_N24_W1, LmOtsMode.LMOTS_SHA256_N24_W2],
            };
            
            var pb = new ParameterBuilder()
                .WithSpecificCapabilities(null)
                .WithGeneralCapabilities(capabilities);
            
            var p = pb.Build();
            var result = _subject.Validate(p);
            Assert.That(result.Success, Is.True, result.ErrorMessage);
        }

        [Test]
        public void WhenGivenSpecificCapabilities_SomeInvalid_ShouldFail()
        {
            var capabilities = new SpecificCapability[]
            {
                new() { LmsMode = LmsMode.LMS_SHA256_M24_H5, LmOtsMode = LmOtsMode.LMOTS_SHA256_N24_W1 },
                new() { LmsMode = LmsMode.LMS_SHA256_M24_H5, LmOtsMode = LmOtsMode.LMOTS_SHA256_N32_W1 }
            };
            var pb = new ParameterBuilder().WithSpecificCapabilities(capabilities);
            var p = pb.Build();
            var result = _subject.Validate(p);
            Assert.That(result.Success, Is.False, result.ErrorMessage);
        }

        [Test]
        public void WhenGivenSpecificCapabilities_MixingHashFunctions_ShouldFail()
        {
            var capabilities = new SpecificCapability[]
            {
                new() { LmsMode = LmsMode.LMS_SHA256_M24_H5, LmOtsMode = LmOtsMode.LMOTS_SHAKE_N24_W1 }
            };
            var pb = new ParameterBuilder().WithSpecificCapabilities(capabilities);
            var p = pb.Build();
            var result = _subject.Validate(p);
            Assert.That(result.Success, Is.False, result.ErrorMessage);
        }

        [Test]
        public void WhenGivenSpecificCapabilities_MixingOutputLengths_ShouldFail()
        {
            var capabilities = new SpecificCapability[]
            {
                new() { LmsMode = LmsMode.LMS_SHA256_M24_H5, LmOtsMode = LmOtsMode.LMOTS_SHA256_N32_W1 }
            };
            var pb = new ParameterBuilder().WithSpecificCapabilities(capabilities);
            var p = pb.Build();
            var result = _subject.Validate(p);
            Assert.That(result.Success, Is.False, result.ErrorMessage);
        }

        [Test]
        public void WhenGivenSpecificCapabilities_InvalidLmsType_ShouldFail()
        {
            var capabilities = new SpecificCapability[]
            {
                new() { LmsMode = LmsMode.Invalid, LmOtsMode = LmOtsMode.LMOTS_SHA256_N24_W1 }
            };
            var pb = new ParameterBuilder().WithSpecificCapabilities(capabilities);
            var p = pb.Build();
            var result = _subject.Validate(p);
            Assert.That(result.Success, Is.False, result.ErrorMessage);
        }

        [Test]
        public void WhenGivenSpecificCapabilities_InvalidLmOtsType_ShouldFail()
        {
            var capabilities = new SpecificCapability[]
            {
                new() { LmsMode = LmsMode.LMS_SHA256_M24_H5, LmOtsMode = LmOtsMode.Invalid }
            };
            var pb = new ParameterBuilder().WithSpecificCapabilities(capabilities);
            var p = pb.Build();
            var result = _subject.Validate(p);
            Assert.That(result.Success, Is.False, result.ErrorMessage);
        }

        [Test]
        public void WhenMessageLengthOutOfBounds_ShouldFail()
        {
            var pb = new ParameterBuilder()
                .WithMessageLength(new MathDomain().AddSegment(new ValueDomainSegment(-1)));
            var p = pb.Build();
            var result = _subject.Validate(p);
            Assert.That(result.Success, Is.False, result.ErrorMessage);
        }
    }
}
