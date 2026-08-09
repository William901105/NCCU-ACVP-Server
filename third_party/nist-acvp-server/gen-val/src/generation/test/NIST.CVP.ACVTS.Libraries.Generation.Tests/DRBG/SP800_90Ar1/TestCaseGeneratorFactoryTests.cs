using System;
using NIST.CVP.ACVTS.Libraries.Generation.DRBG.SP800_90Ar1;
using NIST.CVP.ACVTS.Tests.Core.TestCategoryAttributes;
using NUnit.Framework;

namespace NIST.CVP.ACVTS.Libraries.Generation.Tests.DRBG.SP800_90Ar1
{
    [TestFixture, UnitTest]
    public class TestCaseGeneratorFactoryTests
    {
        [Test]
        [TestCase("Reseed PredResist", true, true, typeof(TestCaseGenerator))]
        [TestCase("Reseed No PredResist", true, false, typeof(TestCaseGenerator))]
        [TestCase("No Reseed PredResist", false, true, typeof(TestCaseGenerator))]
        [TestCase("No Reseed No PredResist", false, false, typeof(TestCaseGenerator))]
        public void ShouldReturnProperGenerator(string label, bool reseed, bool predResist, Type expectedType)
        {
            TestGroup testGroup = new TestGroup()
            {
                ReSeed = reseed,
                PredResistance = predResist
            };

            var subject = new TestCaseGeneratorFactory(null);
            var generator = subject.GetCaseGenerator(testGroup);
            Assert.That(generator, Is.InstanceOf(expectedType));
        }
    }
}
