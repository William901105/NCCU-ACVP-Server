using NIST.CVP.ACVTS.Libraries.Crypto.Common.DRBG.Enums;
using NIST.CVP.ACVTS.Libraries.Generation.DRBG.SP800_90Ar1;
using NIST.CVP.ACVTS.Libraries.Math.Domain;
using NIST.CVP.ACVTS.Tests.Core.TestCategoryAttributes;
using NUnit.Framework;

namespace NIST.CVP.ACVTS.Libraries.Generation.Tests.DRBG.SP800_90Ar1
{
    [TestFixture, UnitTest]
    public class ParameterValidatorTests
    {
        private ParameterValidator _subject;

        [SetUp]
        public void Setup()
        {
            _subject = new ParameterValidator();
        }

        [Test]
        [TestCase(DrbgMechanism.Counter, DrbgMode.AES128)]
        [TestCase(DrbgMechanism.Counter, DrbgMode.AES192)]
        [TestCase(DrbgMechanism.Counter, DrbgMode.AES256)]
        [TestCase(DrbgMechanism.Hash, DrbgMode.SHA1)]
        [TestCase(DrbgMechanism.Hash, DrbgMode.SHA224)]
        [TestCase(DrbgMechanism.Hash, DrbgMode.SHA256)]
        [TestCase(DrbgMechanism.Hash, DrbgMode.SHA384)]
        [TestCase(DrbgMechanism.Hash, DrbgMode.SHA512)]
        [TestCase(DrbgMechanism.Hash, DrbgMode.SHA512t224)]
        [TestCase(DrbgMechanism.Hash, DrbgMode.SHA512t256)]
        public void ShouldValidateSuccessfullyAllValidAlgoAndModes(DrbgMechanism drbgMechanism, DrbgMode drbgMode)
        {
            var p = drbgMechanism == DrbgMechanism.Counter
                ? new ParameterBuilder(drbgMechanism, drbgMode, true).WithCounterFieldLen(128).Build()
                : new ParameterBuilder(drbgMechanism, drbgMode).Build();
            
            var result = _subject.Validate(p);

            Assert.That(result.Success, Is.True, result.ErrorMessage);
        }

        [Test]
        public void ShouldFailValidationWithInvalidDrbgMode()
        {
            var i = -1;
            var invalid = (DrbgMode)i;

            Parameters p = new ParameterBuilder(DrbgMechanism.Counter, invalid).WithCounterFieldLen(128).Build();
            var result = _subject.Validate(p);

            Assert.That(result.Success, Is.False, result.ErrorMessage);
        }

        [Test]
        [TestCase("EntropyInputLen lt test hashDRBG SHA1", DrbgMechanism.Hash, DrbgMode.SHA1, 127, false)]
        [TestCase("EntropyInputLen equal to test hashDRBG SHA1", DrbgMechanism.Hash, DrbgMode.SHA1, 128, true)]
        [TestCase("EntropyInputLen lt test hashDRBG SHA224", DrbgMechanism.Hash, DrbgMode.SHA224, 191, false)]
        [TestCase("EntropyInputLen equal to test hashDRBG SHA224", DrbgMechanism.Hash, DrbgMode.SHA224, 192, true)]
        [TestCase("EntropyInputLen lt test hashDRBG SHA256", DrbgMechanism.Hash, DrbgMode.SHA256, 255, false)]
        [TestCase("EntropyInputLen equal to test hashDRBG SHA256", DrbgMechanism.Hash, DrbgMode.SHA256, 256, true)]
        [TestCase("EntropyInputLen lt test hashDRBG SHA384", DrbgMechanism.Hash, DrbgMode.SHA384, 255, false)]
        [TestCase("EntropyInputLen equal to test hashDRBG SHA384", DrbgMechanism.Hash, DrbgMode.SHA384, 256, true)]        
        [TestCase("EntropyInputLen lt test hashDRBG SHA512", DrbgMechanism.Hash, DrbgMode.SHA512, 255, false)]
        [TestCase("EntropyInputLen equal to test hashDRBG SHA512", DrbgMechanism.Hash, DrbgMode.SHA512, 256, true)]
        [TestCase("EntropyInputLen lt test hashDRBG SHA512t224", DrbgMechanism.Hash, DrbgMode.SHA512t224, 191, false)]
        [TestCase("EntropyInputLen equal to test hashDRBG SHA512t224", DrbgMechanism.Hash, DrbgMode.SHA512t224, 192, true)]     
        [TestCase("EntropyInputLen lt test hashDRBG SHA512t256", DrbgMechanism.Hash, DrbgMode.SHA512t256, 255, false)]
        [TestCase("EntropyInputLen equal to test hashDRBG SHA512t256", DrbgMechanism.Hash, DrbgMode.SHA512t256, 256, true)]   
        public void ShouldFailValidationWhenEntropyLtMin(string label, DrbgMechanism drbgMechanism, DrbgMode drbgMode, int entropyInputLen, bool expectedSuccess)
        {
            ParameterBuilder pb = new ParameterBuilder(drbgMechanism, drbgMode);

            MathDomain md = new MathDomain();
            md.AddSegment(new ValueDomainSegment(entropyInputLen));

            pb.WithDerFunctionEnabled(false)
                .WithEntropyInputLen(md);
            Parameters p = pb.Build();

            var result = _subject.Validate(p);

            Assert.That(result.Success, Is.EqualTo(expectedSuccess), result.ErrorMessage);
        }
        
        
        [Test]
        [TestCase("DefFunc test at seedlen+ ctr aes128", DrbgMechanism.Counter, DrbgMode.AES128, true, true)]
        [TestCase("DefFunc test at seedlen+ ctr aes192", DrbgMechanism.Counter, DrbgMode.AES192, true, true)]
        [TestCase("DefFunc test at seedlen+ ctr aes256", DrbgMechanism.Counter, DrbgMode.AES256, true, true)]
        [TestCase("Not DefFunc test at seedlen+ ctr aes128", DrbgMechanism.Counter, DrbgMode.AES128, false, false)]
        [TestCase("Not DefFunc test at seedlen+ ctr aes192", DrbgMechanism.Counter, DrbgMode.AES192, false, false)]
        [TestCase("Not DefFunc test at seedlen+ ctr aes256", DrbgMechanism.Counter, DrbgMode.AES256, false, false)]
        public void ShouldFailValidationWhenNotDerFuncAndEntropyNotSeedLen(string label, DrbgMechanism drbgMechanism, DrbgMode drbgMode, bool derFunc, bool expectedSuccess)
        {
            ParameterBuilder pb = new ParameterBuilder(drbgMechanism, drbgMode, derFunc).WithCounterFieldLen(128);

            MathDomain md = new MathDomain();
            md.AddSegment(new ValueDomainSegment(pb.SeedLength + 8));

            pb.WithEntropyInputLen(md);
            Parameters p = pb.Build();

            var result = _subject.Validate(p);

            Assert.That(result.Success, Is.EqualTo(expectedSuccess), result.ErrorMessage);
        }

        [Test]
        [TestCase("DefFunc test at seedlen ctr aes128", DrbgMechanism.Counter, DrbgMode.AES128, true, true)]
        [TestCase("DefFunc test at seedlen ctr aes192", DrbgMechanism.Counter, DrbgMode.AES192, true, true)]
        [TestCase("DefFunc test at seedlen ctr aes256", DrbgMechanism.Counter, DrbgMode.AES256, true, true)]
        [TestCase("Not DefFunc test at seedlen ctr aes128", DrbgMechanism.Counter, DrbgMode.AES128, false, true)]
        [TestCase("Not DefFunc test at seedlen ctr aes192", DrbgMechanism.Counter, DrbgMode.AES192, false, true)]
        [TestCase("Not DefFunc test at seedlen ctr aes256", DrbgMechanism.Counter, DrbgMode.AES256, false, true)]
        public void ShouldFailValidationWhenNotDerFuncAndNonceLtHalfSecurityStrength(string label, DrbgMechanism drbgMechanism, DrbgMode drbgMode, bool derFunc, bool expectedSuccess)
        {
            ParameterBuilder pb = new ParameterBuilder(drbgMechanism, drbgMode, derFunc).WithCounterFieldLen(128);

            int mdValue;
            // ctrDRBG with no derFunc is a special case. It's the only case where no nonce is used, i.e., set _nonceLen to 0
            if (drbgMechanism == DrbgMechanism.Counter && !derFunc)
            {
                mdValue = 0;
            }
            else
            {
                mdValue = pb.SecurityStrength / 2 - 8;
            }
            var md = new MathDomain().AddSegment(new ValueDomainSegment(mdValue));
            pb.WithNonceLen(md);
            Parameters p = pb.Build();

            var result = _subject.Validate(p);

            Assert.That(result.Success, Is.EqualTo(expectedSuccess), result.ErrorMessage);
        }

        [Test]
        [TestCase("DefFunc test at seedlen ctr aes128", DrbgMechanism.Counter, DrbgMode.AES128, true, true)]
        [TestCase("DefFunc test at seedlen ctr aes192", DrbgMechanism.Counter, DrbgMode.AES192, true, true)]
        [TestCase("DefFunc test at seedlen ctr aes256", DrbgMechanism.Counter, DrbgMode.AES256, true, true)]
        [TestCase("Not DefFunc test at seedlen ctr aes128", DrbgMechanism.Counter, DrbgMode.AES128, false, false)]
        [TestCase("Not DefFunc test at seedlen ctr aes192", DrbgMechanism.Counter, DrbgMode.AES192, false, false)]
        [TestCase("Not DefFunc test at seedlen ctr aes256", DrbgMechanism.Counter, DrbgMode.AES256, false, false)]
        public void ShouldFailValidationWhenNotDerFuncAndPersoStringNotSeedLen(string label, DrbgMechanism drbgMechanism, DrbgMode drbgMode, bool derFunc, bool expectedSuccess)
        {
            ParameterBuilder pb = new ParameterBuilder(drbgMechanism, drbgMode, derFunc).WithCounterFieldLen(128);

            MathDomain md = new MathDomain();
            md.AddSegment(new ValueDomainSegment(pb.SeedLength + 8));

            pb.WithPersoStringLen(md);
            Parameters p = pb.Build();

            var result = _subject.Validate(p);

            Assert.That(result.Success, Is.EqualTo(expectedSuccess), result.ErrorMessage);
        }

        [Test]
        [TestCase("DefFunc test at seedlen ctr aes128", DrbgMechanism.Counter, DrbgMode.AES128, true, true)]
        [TestCase("DefFunc test at seedlen ctr aes192", DrbgMechanism.Counter, DrbgMode.AES192, true, true)]
        [TestCase("DefFunc test at seedlen ctr aes256", DrbgMechanism.Counter, DrbgMode.AES256, true, true)]
        [TestCase("Not DefFunc test at seedlen ctr aes128", DrbgMechanism.Counter, DrbgMode.AES128, false, false)]
        [TestCase("Not DefFunc test at seedlen ctr aes192", DrbgMechanism.Counter, DrbgMode.AES192, false, false)]
        [TestCase("Not DefFunc test at seedlen ctr aes256", DrbgMechanism.Counter, DrbgMode.AES256, false, false)]
        public void ShouldFailValidationWhenNotDerFuncAndAdditionalInputNotSeedLen(string label, DrbgMechanism drbgMechanism, DrbgMode drbgMode, bool derFunc, bool expectedSuccess)
        {
            ParameterBuilder pb = new ParameterBuilder(drbgMechanism, drbgMode, derFunc).WithCounterFieldLen(128);

            MathDomain md = new MathDomain();
            md.AddSegment(new ValueDomainSegment(pb.SeedLength + 8));

            pb.WithAdditionalInputLen(md);
            Parameters p = pb.Build();

            var result = _subject.Validate(p);

            Assert.That(result.Success, Is.EqualTo(expectedSuccess), result.ErrorMessage);
        }

        [Test]
        [TestCase(0, 0, true)]
        [TestCase(1, 0, false)]
        [TestCase(0, 1, false)]
        [TestCase(1, 1, false)]
        public void ShouldValidateNonceLenWhenCtrDrbgAndDerFuncFalse(int nonceMin, int nonceMax, bool expectedSuccess)
        {
            ParameterBuilder pb = new ParameterBuilder(DrbgMechanism.Counter, DrbgMode.AES128, false).WithCounterFieldLen(128);
            
            MathDomain md = new MathDomain();
            md.AddSegment(new ValueDomainSegment(nonceMin));
            md.AddSegment(new ValueDomainSegment(nonceMax));
            
            pb.WithNonceLen(md);
            Parameters p = pb.Build();

            var result = _subject.Validate(p);

            Assert.That(result.Success, Is.EqualTo(expectedSuccess), result.ErrorMessage);
        }

        [Test]
        [TestCase("entropy + nonce < 3/2 security strength", 128, 0, false)]
        [TestCase("entropy = security strength, nonce = 1/2 security strength", 128, 64, true)]
        [TestCase("entropy > security strength, nonce < 1/2 security strength, & entropy + nonce >= 3/2 security strength", 192, 0, true)]
        public void ShouldValidateEntropyPlusNonceGTEThreeHalvesSecurityStrength(string label, int minEntropyInputLen,
            int minNonceLen, bool expectedSuccess)
        {
            ParameterBuilder pb = new ParameterBuilder(DrbgMechanism.Counter, DrbgMode.AES128, true).WithCounterFieldLen(128);
            
            var entropyDomain = new MathDomain().AddSegment(new ValueDomainSegment(minEntropyInputLen));
            var nonceDomain = new MathDomain().AddSegment(new ValueDomainSegment(minNonceLen));

            pb.WithEntropyInputLen(entropyDomain).WithNonceLen(nonceDomain);
            Parameters p = pb.Build();

            var result = _subject.Validate(p);

            Assert.That(result.Success, Is.EqualTo(expectedSuccess), result.ErrorMessage);
        }
        
        [Test]
        public void ShouldFailValidationWithNoReturnedBitsLenProvided()
        {
            ParameterBuilder pb = new ParameterBuilder(DrbgMechanism.Counter, DrbgMode.AES256, true);
            
            pb.WithReturnedBitsLen(null);
            Parameters p = pb.Build();
            var result = _subject.Validate(p);
            
            //System.Console.WriteLine($"Error message: {result.ErrorMessage}");
            Assert.That(result.Success, Is.False, result.ErrorMessage);
        }
        
        [Test]
        public void ShouldFailValidationWithMinReturnedBitsLenLessThanOutLen()
        {
            ParameterBuilder pb = new ParameterBuilder(DrbgMechanism.Counter, DrbgMode.AES256, true);
            
            // outlen = blocklen for ctrDRBG. For AES, outlen = 128. Parameter Validation should fail if returnedBitsLen
            // includes any value(s) less than 128. 
            var returnedBitsLenDomain = new MathDomain().AddSegment(new ValueDomainSegment(64));
            
            pb.WithReturnedBitsLen(returnedBitsLenDomain);
            Parameters p = pb.Build();
            var result = _subject.Validate(p);
            
            //System.Console.WriteLine($"Error message: {result.ErrorMessage}");
            Assert.That(result.Success, Is.False, result.ErrorMessage);
        }
        
        [Test]
        public void ShouldFailValidationWithMaxReturnedBitsLenGreaterThanMaxOutputSize()
        {
            ParameterBuilder pb = new ParameterBuilder(DrbgMechanism.Counter, DrbgMode.AES256, true);
            
            // For hash and hmac drbgs, per SP800-90Ar1 Table 2, the maximum allowed value of returnedBitsLen is 2^19 bits.
            // For ctr drbgs, per Table 3, the maximum value of returnedBitsLen is min(B, 2^19) bits for AES and min(B, 2^13)
            // bits for TDES where B = (2^ctr_len - 4) x blocklen. As values such as 2^19 and 2^13 are quite large, we
            // arbitrarily cap the maximum value of returnedBitsLen at MaxOutputSize or 4096 bits. Parameter Validation
            // should fail if returnedBitsLen includes any value(s) greater than 4096. 
            var returnedBitsLenDomain = new MathDomain().AddSegment(new ValueDomainSegment(5000));
            
            pb.WithReturnedBitsLen(returnedBitsLenDomain);
            Parameters p = pb.Build();
            var result = _subject.Validate(p);
            
            //System.Console.WriteLine($"Error message: {result.ErrorMessage}");
            Assert.That(result.Success, Is.False, result.ErrorMessage);
        }
        
        [Test]
        public void ShouldFailValidationWithCtrDrbgMaxReturnedBitsLenGreaterThanB()
        {
            ParameterBuilder pb = new ParameterBuilder(DrbgMechanism.Counter, DrbgMode.AES256, true);
            
            // For ctr drbgs, per Table 3, the maximum value of returnedBitsLen is min(B, 2^19) bits for AES
            // where B = (2^ctr_len - 4) x blocklen. As values such as 2^19 and 2^13 are quite large, we
            // arbitrarily cap the maximum value of returnedBitsLen at MaxOutputSize or 4096 bits.
            // When counterFieldLen = 4 bits, B = (2^4 - 4) x 128 = 1536 bits. 
            // If counterFieldLen = 4 bits, Parameter Validation should fail if returnedBitsLen includes any value(s)
            // between 1537 and 4096 bits. 
            var returnedBitsLenDomain = new MathDomain().AddSegment(new ValueDomainSegment(2000));
            pb.WithReturnedBitsLen(returnedBitsLenDomain);
            pb.WithCounterFieldLen(4);
            Parameters p = pb.Build();
            var result = _subject.Validate(p);
            
            //System.Console.WriteLine($"Error message: {result.ErrorMessage}");
            Assert.That(result.Success, Is.False, result.ErrorMessage);
        }
        
         [Test]
        [TestCase("ctrDRBG AES128 should fail with counterFieldLength < 4 ", DrbgMode.AES128, 1, false)]
        [TestCase("ctrDRBG AES192 should pass with  4 <= counterFieldLength <= 128", DrbgMode.AES192,96, true)]
        [TestCase("ctrDRBG AES256 should fail with counterFieldLength > 128", DrbgMode.AES256, 192, false)]
        [TestCase("ctrDRBG TDES should pass with counterFieldLength 4 <= counterFieldLength <= 64", DrbgMode.TDES, 4, true)]
        [TestCase("ctrDRBG TDES should fail with counterFieldLength > 64", DrbgMode.TDES, 96, false)]
         [TestCase("ctrDRBG should fail with no counterFieldLength", DrbgMode.TDES, null, false)]
        public void ShouldValidateCounterFieldLenForCtrDrbg(string label, DrbgMode drbgMode, int? counterFieldLen, bool expectedSuccess)
        {
            ParameterBuilder pb = new ParameterBuilder(DrbgMechanism.Counter, drbgMode, true);
            
            pb.WithCounterFieldLen(counterFieldLen);
            Parameters p = pb.Build();

            var result = _subject.Validate(p);

            Assert.That(result.Success, Is.EqualTo(expectedSuccess), result.ErrorMessage);
        }
    }
}
