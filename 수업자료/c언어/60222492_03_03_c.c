#include <stdio.h>
void main(){
	char name;
	int age;
	double weight;
	
	printf("자신의 이름의 영문 이니셜을 입력하시오:");
	scanf("%c",&name);
	printf("당신의 나이와 몸무게를 입력하시오:");
	scanf("%d%lf",&age,&weight);
	printf("이름의 영문 이니셜은 %c, 나이는 %d세, 몸무게는 %lf 입니다. ",name,age,weight);
	
}
